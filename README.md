# PREDIF ESP32 Motor Predictive Maintenance System

## Overview
PREDIF is an **AI-powered predictive maintenance system** for industrial motors. This folder contains:
- **Backend Server** (`server.py`) - FastAPI server with ML inference
- **ML Training** (`train_model.py`) - Random Forest classifier training
- **Web Dashboard** (`index.html`) - Real-time monitoring interface
- **ESP32 Firmware** (`esp32_firmware.ino`) - Embedded sensor acquisition & actuation
- **Sample Data** (`motor_fault_data.csv`) - Training dataset

## System Architecture

### Four-Layer Stack
```
┌─────────────────────────────────────────────┐
│        WEB DASHBOARD (HTML/JS)              │  ← Real-time monitoring & control
├─────────────────────────────────────────────┤
│     FASTAPI SERVER (Python)                 │  ← ML inference, WebSocket updates
├─────────────────────────────────────────────┤
│  RANDOM FOREST MODEL (scikit-learn)         │  ← Predictive classification
├─────────────────────────────────────────────┤
│  ESP32 MICROCONTROLLER (Arduino)            │  ← Sensor acquisition & actuation
│  ├─ DHT11 (Temperature)                     │
│  ├─ ADXL345 (3-axis Vibration)              │
│  ├─ Relay (Motor Disconnect)                │
│  └─ Transistor (Cooling Fan PWM)            │
└─────────────────────────────────────────────┘
```

---

## Hardware Wiring for ESP32

### Components Required
- **ESP32 DevKit** (main microcontroller)
- **DHT11 Temperature Sensor** (or DHT22 for better accuracy)
- **ADXL345 3-axis Accelerometer** (I2C interface)
- **5V Relay Module** (motor disconnect)
- **BC547 NPN Transistor** (cooling fan PWM control)
- **1N4007 Diode** (relay protection)
- **10kΩ Resistor** (DHT11 pull-up, optional if module has built-in)
- **1kΩ Resistor** (transistor base limiting)
- **Connecting wires, breadboard, 5V power supply**

### Wiring Diagram

```
ESP32 PINOUT (Top View):
┌─────────────────────────────────┐
│ GND  3V3  EN  RST  D35  D34     │
│ D36  D39  D25  D26  D27  D14   │  ← D25 = RELAY, D26 = FAN (PWM)
│ D12  D13   D9  D10  D11  D6    │
│ D7   D8   D5   D4   D3   D1    │  ← D4 = DHT11, D3/D1 = UART
│ D2   D15  D16  D17 D5V  GND   │
│ 5V   GND  GND  GND  GND  GND   │
└─────────────────────────────────┘

┌────────────────────────────────────────────────────────────┐
│                      CONNECTIONS                           │
├────────────────────────────────────────────────────────────┤
│ DHT11 (Temperature Sensor)                                 │
│   VCC  → ESP32 3V3                                         │
│   GND  → ESP32 GND                                         │
│   DATA → ESP32 D4 (GPIO4)                                  │
│   (Optional: 10kΩ pull-up between DATA and 3V3)           │
│                                                            │
│ ADXL345 (Vibration Sensor - I2C)                           │
│   VCC  → ESP32 3V3                                         │
│   GND  → ESP32 GND                                         │
│   SDA  → ESP32 D21 (GPIO21 / SDA)                          │
│   SCL  → ESP32 D22 (GPIO22 / SCL)                          │
│   CS   → ESP32 3V3 (Force I2C mode)                        │
│   INT1/INT2 → (Optional, not used in basic setup)         │
│                                                            │
│ RELAY Module (5V, for motor disconnect)                    │
│   VCC  → 5V power supply                                   │
│   GND  → GND (common with ESP32)                           │
│   IN   → ESP32 D25 (GPIO25)                                │
│   COM  → Motor phase A                                     │
│   NO   → (Normally Open, not used)                         │
│   NC   → Motor supply (cuts power when relay ON)           │
│                                                            │
│ BC547 Transistor (for cooling fan PWM)                     │
│   Collector → Cooling fan (+)                              │
│   Emitter  → GND (via 1N4007 diode cathode)               │
│   Base     → ESP32 D26 (GPIO26) via 1kΩ resistor         │
│   (1N4007 diode between fan GND and transistor emitter)   │
│                                                            │
│ Motor Load                                                 │
│   Phase A  → Relay COM                                     │
│   Phase B/C → Power supply (always connected)             │
│                                                            │
└────────────────────────────────────────────────────────────┘
```

### Circuit Diagram (Text Format)

```
┌─────────────────────┐
│      ESP32          │
│  3V3  GND  D4       │
│   │    │    │       │
│   └────┼────┘       │
│        │            │
│   ┌────┴────┐       │
│   │  DHT11  │       │
│   │   T°C   │       │
│   └─────────┘       │
│                     │
│  D21 D22 (I2C)      │
│   │    │            │
│   └────┬────────┐   │
│        │        │   │
│    ┌───────────┐│   │
│    │  ADXL345  ││   │
│    │  Vibrat°  ││   │
│    │ (I2C)    ││   │
│    └───────────┘│   │
│        │        │   │
│       GND  +3V3┘   │
│                     │
│  D25 (GPIO)         │
│   │                 │
│   ├──────┐          │
│   │      │          │
│   │   [1kΩ]         │ D26 PWM
│   │      │          │  │
│   │     [RELAY]    [BC547]
│   │      │          │ │ │
│   │    MOTOR    FAN │ │
│   │                 │ │
│   └─────────────────┴─┘
│        ↓↓ MOTOR PHASES
│
└─────────────────────┘
```

---

## Software Setup

### 1. Python Backend Setup

#### Install Dependencies
```bash
cd C:\Users\SAYAK\Downloads\Predif_ESP32
pip install -r requirements.txt
```

#### Train ML Model
```bash
python train_model.py
```
This generates `rf_model.pkl` (Random Forest classifier).

#### Run Server
```bash
python server.py
```
The server starts on `http://localhost:8000`
- WebSocket: `ws://localhost:8000/ws`
- API: `http://localhost:8000/api/state`
- Dashboard: `http://localhost:8000/`

### 2. ESP32 Firmware Setup

#### Prerequisites
- **Arduino IDE** v1.8.19+ or **VS Code + PlatformIO**
- **ESP32 Board Package** installed

#### Required Arduino Libraries
Install via **Sketch → Include Library → Manage Libraries**:
- `WiFi` (built-in)
- `DHT sensor library` (by Adafruit) v1.4.4+
- `Adafruit Unified Sensor` v1.1.14+
- `Adafruit ADXL345` v1.0.4+
- `ArduinoJson` v6.21+
- `HTTPClient` (built-in)

#### Configuration
Open `esp32_firmware.ino` and edit:
```cpp
const char* ssid = "YOUR_SSID";              // Your WiFi SSID
const char* password = "YOUR_PASSWORD";      // Your WiFi password
const char* serverURL = "http://192.168.1.X:8000/api/state";  // Server IP
```

#### Upload Firmware
1. Connect ESP32 via USB
2. **Tools → Board → ESP32 Dev Module**
3. **Tools → Port → COM3** (or appropriate port)
4. **Sketch → Upload**

#### Monitor Serial Output
- **Tools → Serial Monitor**
- Baud Rate: **115200**

Expected output:
```
=== PREDIF ESP32 MOTOR FAULT DETECTION ===
[DHT11] Temperature sensor initialized on GPIO 4
[ADXL345] Accelerometer initialized on I2C SDA=21 SCL=22
Connecting to WiFi: YOUR_SSID
[WiFi OK] Connected!
IP Address: 192.168.1.100
[READY] All systems initialized. Starting sensor loop...

[SENSORS] T=35.2°C | Vib_RMS=0.234g | ML_Label=NORMAL (92.3%) | Motor=RUNNING
```

---

## API Endpoints

### `GET /api/state`
Fetch current dashboard state (used by ESP32 and web UI)

**Response:**
```json
{
  "temperature_C": 42.5,
  "vib_rms_g": 0.312,
  "ml_label": 0,
  "ml_label_name": "NORMAL",
  "ml_confidence_pct": 87.5,
  "locked": false,
  "adaptive_temp_threshold": 45.0,
  "adaptive_vib_threshold": 0.25,
  "action_log": [...]
}
```

### `POST /api/control/reset`
Clear lockout after inspection

### `WebSocket /ws`
Real-time dashboard updates (continuous JSON stream)

---

## Operation

### Normal Operation Flow
1. **Sensor Acquisition** (ESP32 every 500ms)
   - DHT11 reads temperature
   - ADXL345 reads 3-axis acceleration → calculates RMS

2. **Server Inference** (continuous)
   - Receives sensor data from CSV playback
   - Random Forest predicts: NORMAL or CRITICAL
   - Simulated Annealing optimizes thresholds every 5 minutes

3. **Actuation** (ESP32 every 2 seconds)
   - Fetches prediction from `/api/state`
   - **NORMAL**: Motor ON, fan PWM proportional to temp
   - **CRITICAL**: Motor LOCKED (relay OFF), fan MAX (PWM 255)

4. **Monitoring** (Web Dashboard)
   - WebSocket receives live telemetry
   - Charts update every 250ms
   - Action log records all events

### Emergency States
| Condition | Action | Duration |
|-----------|--------|----------|
| Temp ≥ 45°C OR Vib ≥ 0.25g | CRITICAL | Until manual RESET |
| Motor LOCKED | Cooling fan ON 100% | Until inspection + RESET |
| WiFi disconnected | Relay defaults to motor ON | Manual override required |

---

## Troubleshooting

### ESP32 Issues

#### **Sensor not responding**
```
[ERROR] ADXL345 not found!
```
- Check I2C wiring (SDA/SCL)
- Verify CS pin is tied to 3V3 (I2C mode)
- Try I2C scanner:
  ```cpp
  // Add to setup()
  Wire.begin(21, 22);
  for (addr = 1; addr < 127; addr++) {
    Wire.beginTransmission(addr);
    if (Wire.endTransmission() == 0) {
      Serial.print("Found device at 0x");
      Serial.println(addr, HEX);
    }
  }
  ```

#### **WiFi connection fails**
- Check SSID/password spelling
- Ensure 2.4GHz WiFi (ESP32 not compatible with 5GHz)
- Move closer to router
- Check firewall allows port 8000

#### **Server unreachable**
```
[HTTP ERROR] Code: -1
```
- Verify server running: `curl http://localhost:8000/api/state`
- Check firewall: `netsh advfirewall firewall add rule name="PREDIF" dir=in action=allow protocol=tcp localport=8000`
- Verify IP address in firmware matches server machine

### Python Server Issues

#### **Model not found**
```
FileNotFoundError: Train first: python train_model.py
```
- Run `python train_model.py` in the project folder

#### **CSV file missing**
- Ensure `motor_fault_data.csv` is in the same directory as `server.py`

#### **Port already in use**
```
Address already in use
```
- Change port: `uvicorn server:app --host 0.0.0.0 --port 8001`
- Or kill existing process: `netstat -ano | findstr :8000`

---

## Performance Metrics

| Component | Latency | Update Rate |
|-----------|---------|------------|
| DHT11 sensor | ~2 sec | 0.5 Hz (500ms) |
| ADXL345 sensor | ~1 ms | 2 Hz (500ms) |
| ESP32 → Server | ~100-200 ms | 0.5 Hz (2 sec) |
| Server inference | ~10 ms | 3.3 Hz (CSV playback) |
| Web dashboard | ~250 ms | 4 Hz (WebSocket) |
| **Total response** | **~200-300 ms** | **3-4 Hz** |

---

## Dataset Format (`motor_fault_data.csv`)

Required columns:
- `temperature_C` - Motor winding temperature (20-85°C)
- `vib_x_g`, `vib_y_g`, `vib_z_g` - 3-axis acceleration (±16g range)
- `vib_rms_g` - Pre-calculated RMS vibration
- `label` - Ground truth (0=NORMAL, 1=CRITICAL)

Example:
```csv
temperature_C,vib_x_g,vib_y_g,vib_z_g,vib_rms_g,label
35.2,0.12,0.18,0.14,0.15,0
52.8,0.68,0.72,0.65,0.68,1
42.1,0.24,0.31,0.28,0.28,0
```

---

## Deployment

### Local Network
```bash
# On server machine
python server.py

# On browser
http://192.168.1.X:8000  (replace X with server IP)

# ESP32 connects via WiFi and fetches /api/state
```

### Docker Deployment (Optional)
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY . .
RUN pip install -r requirements.txt
EXPOSE 8000
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
```

```bash
docker build -t predif .
docker run -p 8000:8000 predif
```

---

## License & Attribution
**PREDIF** - Predictive Maintenance Framework  
**Version:** 6.1.0  
**Author:** Applied Electronics & Instrumentation Engineering

---

## Contact & Support
For issues or questions:
1. Check **Troubleshooting** section above
2. Review ESP32 **Serial Monitor** for error codes
3. Verify server logs: `tail -f /tmp/predif.log`
4. Contact: [your contact info]
