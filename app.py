import csv
import json
import os
import threading
from datetime import datetime, timezone

from flask import Flask, jsonify, render_template, request

LOG_PATH = os.getenv("LOG_PATH", "smart_campus_log.csv")

app = Flask(__name__)
latest = {
    "device_id": "waiting",
    "temperature_c": None,
    "humidity_pct": None,
    "air_quality_raw": None,
    "motion": None,
    "current_a": None,
    "power_w": None,
    "received_at": None,
}
latest_lock = threading.Lock()


def append_log(data):
    file_exists = os.path.exists(LOG_PATH)
    fieldnames = [
        "received_at",
        "device_id",
        "temperature_c",
        "humidity_pct",
        "air_quality_raw",
        "motion",
        "current_a",
        "power_w",
    ]
    with open(LOG_PATH, "a", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        row = {key: data.get(key) for key in fieldnames}
        writer.writerow(row)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/telemetry", methods=["POST"])
def api_telemetry():
    data = request.get_json(force=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Invalid payload"}), 400

    data["received_at"] = datetime.now(timezone.utc).isoformat()
    with latest_lock:
        latest.clear()
        latest.update(data)

    append_log(data)
    return jsonify({"ok": True})


@app.route("/api/latest")
def api_latest():
    with latest_lock:
        return jsonify(latest)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)

