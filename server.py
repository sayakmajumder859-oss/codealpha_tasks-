from __future__ import annotations

import asyncio
import logging
import math
import random
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any

import joblib
import pandas as pd
from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

ROOT_DIR = Path(__file__).parent.resolve()
load_dotenv(ROOT_DIR / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("predif")

MODEL_PATH = ROOT_DIR / "rf_model.pkl"
CSV_PATH = ROOT_DIR / "motor_fault_data.csv"
PLAYBACK_INTERVAL_S = 0.3

DEFAULT_TEMP_TH = 45.0
DEFAULT_VIB_TH = 0.25

state_lock = threading.Lock()
dashboard: dict[str, Any] = {
    "temperature_C": None,
    "vib_rms_g": None,
    "ml_label": 0,
    "ml_label_name": "NORMAL",
    "ml_confidence_pct": 0.0,
    "command_sent": "—",
    "locked": False,
    "data_source": str(CSV_PATH.name),
    "sample_index": 0,
    "csv_total_rows": 0,
    "adaptive_temp_threshold": DEFAULT_TEMP_TH,
    "adaptive_vib_threshold": DEFAULT_VIB_TH,
    "last_sa_run_utc": None,
    "action_log": [],
}

history: deque[tuple[float, float, int]] = deque(maxlen=600)
reset_flag = threading.Event()


def _log_action(message: str) -> None:
    ts = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())
    entry = {"ts_utc": ts, "message": message}
    with state_lock:
        log = dashboard["action_log"]
        log.insert(0, entry)
        del log[80:]


def load_model():
    if not MODEL_PATH.is_file():
        raise FileNotFoundError(f"Train first: python train_model.py — missing {MODEL_PATH}")
    bundle = joblib.load(MODEL_PATH)
    return bundle["model"], bundle.get("features", ["temperature_C", "vib_rms_g"])


try:
    rf_model, feature_names = load_model()
except Exception as e:
    logger.error("%s", e)
    rf_model, feature_names = None, ["temperature_C", "vib_rms_g"]


def predict_rf(temp_c: float, vib_g: float) -> tuple[int, float]:
    if rf_model is None:
        lbl = 1 if (temp_c >= DEFAULT_TEMP_TH or vib_g >= DEFAULT_VIB_TH) else 0
        conf = 1.0 if lbl == 1 else 0.85
        return lbl, conf * 100.0
    X = pd.DataFrame([[temp_c, vib_g]], columns=feature_names)
    proba = rf_model.predict_proba(X)[0]
    lbl = int(rf_model.predict(X)[0])
    conf = float(max(proba))
    return lbl, conf * 100.0


def rule_fault(temp_c: float, vib_g: float, t_th: float, v_th: float) -> int:
    return 1 if (temp_c >= t_th or vib_g >= v_th) else 0


def simulated_annealing_thresholds(
    samples: list[tuple[float, float, int]],
    t0: float,
    v0: float,
) -> tuple[float, float]:
    if len(samples) < 10:
        return t0, v0

    def energy(tt: float, vv: float) -> float:
        err = 0.0
        for temp_c, vib_g, y_rf in samples:
            y_rule = rule_fault(temp_c, vib_g, tt, vv)
            err += (y_rule - y_rf) ** 2
        err += 0.02 * abs(tt - DEFAULT_TEMP_TH) + 0.5 * abs(vv - DEFAULT_VIB_TH)
        return err

    t_sa = 2.0
    cur_t, cur_v = t0, v0
    cur_e = energy(cur_t, cur_v)
    best_t, best_v, best_e = cur_t, cur_v, cur_e
    for _ in range(2500):
        nt = max(25.0, min(85.0, cur_t + random.gauss(0, 1.2)))
        nv = max(0.08, min(1.2, cur_v + random.gauss(0, 0.02)))
        ne = energy(nt, nv)
        de = ne - cur_e
        if de < 0 or random.random() < math.exp(-de / max(t_sa, 1e-6)):
            cur_t, cur_v, cur_e = nt, nv, ne
            if ne < best_e:
                best_t, best_v, best_e = nt, nv, ne
        t_sa *= 0.997
    return best_t, best_v


def send_command(cmd: str) -> None:
    with state_lock:
        dashboard["command_sent"] = cmd.strip().upper()


def csv_playback_loop() -> None:
    if not CSV_PATH.is_file():
        logger.error("Missing %s — cannot play back telemetry.", CSV_PATH)
        with state_lock:
            dashboard["csv_total_rows"] = 0
        return

    df = pd.read_csv(CSV_PATH)
    if "temperature_C" not in df.columns or "vib_rms_g" not in df.columns:
        logger.error("CSV must include temperature_C and vib_rms_g columns.")
        with state_lock:
            dashboard["csv_total_rows"] = 0
        return

    n = len(df)
    order = list(range(n))
    random.shuffle(order)
    pos = 0

    with state_lock:
        dashboard["csv_total_rows"] = n
    logger.info("Playback: %s (%d rows), %.0f ms per sample.", CSV_PATH.name, n, PLAYBACK_INTERVAL_S * 1000)
    _log_action(f"Telemetry from {CSV_PATH.name} ({n} rows), shuffled loop.")

    while True:
        if reset_flag.is_set():
            reset_flag.clear()
            with state_lock:
                dashboard["locked"] = False
            send_command("RESET")
            _log_action("RESET: lockout cleared.")

        idx = order[pos % len(order)]
        pos += 1
        row = df.iloc[idx]
        temp_c = float(row["temperature_C"])
        vib_g = float(row["vib_rms_g"])

        with state_lock:
            dashboard["sample_index"] = int(idx)

        process_sample(temp_c, vib_g)
        time.sleep(PLAYBACK_INTERVAL_S)


def process_sample(temp_c: float, vib_g: float) -> None:
    lbl, conf = predict_rf(temp_c, vib_g)
    name = "CRITICAL" if lbl == 1 else "NORMAL"

    with state_lock:
        at = dashboard["adaptive_temp_threshold"]
        av = dashboard["adaptive_vib_threshold"]
        was_locked = dashboard["locked"]

    rule_crit = rule_fault(temp_c, vib_g, at, av)
    critical_ml = lbl == 1 or rule_crit == 1

    with state_lock:
        dashboard["temperature_C"] = round(temp_c, 2)
        dashboard["vib_rms_g"] = round(vib_g, 4)
        dashboard["ml_label"] = lbl
        dashboard["ml_label_name"] = name
        dashboard["ml_confidence_pct"] = round(conf, 2)
        if critical_ml and not was_locked:
            dashboard["locked"] = True
        locked_now = dashboard["locked"]
        history.append((temp_c, vib_g, lbl))

    if critical_ml and not was_locked:
        _log_action(
            f"CRITICAL / LOCKOUT: temp={temp_c:.1f}°C vib={vib_g:.3f}g "
            f"(adaptive thresholds {at:.1f}°C, {av:.3f}g)."
        )

    if locked_now:
        send_command("CRITICAL")
    else:
        send_command("NORMAL")


threading.Thread(target=csv_playback_loop, daemon=True).start()


async def sa_periodic_task() -> None:
    await asyncio.sleep(15)
    while True:
        await asyncio.sleep(300)
        with state_lock:
            snap = list(history)
            t0 = dashboard["adaptive_temp_threshold"]
            v0 = dashboard["adaptive_vib_threshold"]
        if len(snap) < 20:
            continue
        nt, nv = simulated_annealing_thresholds(snap, t0, v0)
        with state_lock:
            dashboard["adaptive_temp_threshold"] = round(nt, 2)
            dashboard["adaptive_vib_threshold"] = round(nv, 4)
            dashboard["last_sa_run_utc"] = time.strftime(
                "%Y-%m-%d %H:%M:%S UTC", time.gmtime()
            )
        _log_action(
            f"Simulated annealing: adaptive thresholds → {nt:.2f}°C, {nv:.4f}g RMS."
        )
        logger.info("SA updated thresholds: temp>=%.2f vib>=%.4f", nt, nv)


app = FastAPI(title="PREDIF Motor Fault Control")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def _startup() -> None:
    asyncio.create_task(sa_periodic_task())
    _log_action("Backend started; live feed from motor_fault_data.csv.")


@app.post("/api/control/reset")
async def api_reset() -> dict:
    reset_flag.set()
    _log_action("Manual RESET requested from dashboard/API.")
    return {"ok": True, "message": "RESET applied on next playback tick."}


@app.get("/api/state")
async def api_state() -> dict:
    with state_lock:
        return {k: v for k, v in dashboard.items() if k != "action_log"} | {
            "action_log": list(dashboard["action_log"][:40]),
        }


@app.websocket("/ws")
async def websocket_dashboard(ws: WebSocket) -> None:
    await ws.accept()
    try:
        while True:
            with state_lock:
                payload = {
                    "temperature_C": dashboard["temperature_C"],
                    "vib_rms_g": dashboard["vib_rms_g"],
                    "ml_label": dashboard["ml_label"],
                    "ml_label_name": dashboard["ml_label_name"],
                    "ml_confidence_pct": dashboard["ml_confidence_pct"],
                    "command_sent": dashboard["command_sent"],
                    "locked": dashboard["locked"],
                    "data_source": dashboard["data_source"],
                    "sample_index": dashboard["sample_index"],
                    "csv_total_rows": dashboard["csv_total_rows"],
                    "adaptive_temp_threshold": dashboard["adaptive_temp_threshold"],
                    "adaptive_vib_threshold": dashboard["adaptive_vib_threshold"],
                    "last_sa_run_utc": dashboard["last_sa_run_utc"],
                    "action_log": list(dashboard["action_log"][:40]),
                }
            await ws.send_json(payload)
            await asyncio.sleep(0.25)
    except WebSocketDisconnect:
        pass


@app.get("/")
async def serve_index() -> FileResponse:
    return FileResponse(ROOT_DIR / "index.html")


app.mount("/static", StaticFiles(directory=str(ROOT_DIR), html=False), name="assets")
