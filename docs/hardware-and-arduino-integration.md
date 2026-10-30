# Hardware and Arduino Integration Guide

## 1. Overview and Architecture

The **TwinVolt Universal Battery Digital Twin Platform** provides real-time monitoring, state estimation (SOC, SOH, SOP), and electro-thermal digital twin simulation. 

To bridge physical battery testbenches (microcontroller BMS prototypes, Arduino/ESP32 sensor rigs) with the cloud/desktop analytics platform, TwinVolt employs a **Local Hardware Gateway Architecture**.

```text
┌────────────────────────────────────────────────────────┐
│             Physical Battery Testbench                 │
│  [Pack / Cells] <-> [Sensors] <-> [Arduino / ESP32]    │
└───────────────────────────┬────────────────────────────┘
                            │ USB Serial (UART)
                            ▼
┌────────────────────────────────────────────────────────┐
│             Local Hardware Gateway                     │
│           (Runs on user's local machine)               │
│                                                        │
│  ┌────────────────────┐      ┌──────────────────────┐  │
│  │ SerialTransport    │ ---> │ ArduinoFrameParser   │  │
│  │ (Async PySerial)   │      │ (JSON / CSV / Auto)  │  │
│  └────────────────────┘      └──────────┬───────────┘  │
│                                         │ Validated    │
│                                         ▼ Records      │
│  ┌──────────────────────────────────────────────────┐  │
│  │              ArduinoConnectionManager            │  │
│  │      - Dynamic COM Port Scan & Supervisor        │  │
│  │      - Stale Data & Sampling Rate Tracking       │  │
│  └──────────────────────┬───────────────────────────┘  │
└─────────────────────────┼──────────────────────────────┘
                          │ Ingests Canonical Telemetry
                          ▼
┌────────────────────────────────────────────────────────┐
│             TwinVolt Core Telemetry Pipeline           │
│                                                        │
│  ┌──────────────────┐      ┌────────────────────────┐  │
│  │ TelemetryService │ ---> │ State Estimators (EKF) │  │
│  └────────┬─────────┘      └───────────┬────────────┘  │
│           │                            │               │
│           ▼                            ▼               │
│  ┌──────────────────────────────────────────────────┐  │
│  │        FastAPI REST & WebSocket Real-time API    │  │
│  └──────────────────────┬───────────────────────────┘  │
└─────────────────────────┼──────────────────────────────┘
                          │ WebSocket / JSON Streams
                          ▼
┌────────────────────────────────────────────────────────┐
│           TwinVolt Web Frontend (HTML5/ES6)            │
│                                                        │
│  - Live Telemetry Dashboard (Voltage, Current, Temp)   │
│  - Hardware & Firmware Workspace (/ui/hardware)        │
│  - Isolated Mock Telemetry Generator (/ui/mock)        │
│  - Real-time Charts, Event Logs & Data Export          │
└────────────────────────────────────────────────────────┘
```

---

## 2. Remote vs. Local Hardware Boundary Notice

> [!IMPORTANT]
> **Serial Port Access Boundary:**
> Web browsers and remotely hosted cloud servers **cannot directly access a USB serial COM port** on a client computer due to browser sandboxing and network isolation.
>
> Therefore, the TwinVolt backend or a local TwinVolt Edge Gateway instance **must run locally on the workstation physically connected to the Arduino via USB**.
>
> When the local gateway runs on the user's machine (`http://127.0.0.1:8000`), it reads the USB serial device natively via `pyserial`, validates and packages the data, and broadcasts it over WebSockets to both local and remote dashboard interfaces.

---

## 3. Local Development Setup & Prerequisites

### 3.1 System Requirements
- **OS**: Windows 10/11, macOS, or Linux
- **Python**: Python 3.11, 3.12, 3.13, or 3.14
- **Microcontroller**: Arduino Uno, Mega, Nano, ESP32, STM32, or any UART-compatible MCU
- **Hardware Connection**: Standard USB-A / USB-C cable to microcontroller

### 3.2 Python Virtual Environment and Dependencies
Install all required packages from `requirements.txt`:

```bash
# Optional: Create and activate virtual environment
python -m venv .venv
# Windows PowerShell:
.venv\Scripts\Activate.ps1
# Linux / macOS:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

Core dependencies include:
- `fastapi`, `uvicorn`: Asynchronous web server and WebSocket broadcaster.
- `pyserial`: Hardware serial port communication.
- `pydantic`: Schema validation and type safety.
- `numpy`, `scipy`: Digital twin electro-thermal and EKF estimation.
- `pytest`, `pytest-asyncio`: Automated test suites.

### 3.3 Configuration
Copy the template configuration file:
```bash
cp .env.example .env
```
Key configuration settings in `.env`:
```ini
TWINVOLT_ENV=development
API_HOST=127.0.0.1
API_PORT=8000
DEBUG=True
LOG_LEVEL=INFO
SERIAL_DEFAULT_BAUD=115200
```

---

## 4. Starting the Platform

### 4.1 Backend & Built-in UI
Start the TwinVolt unified backend server:

```bash
python -m src.server --host 127.0.0.1 --port 8000
```

Once started:
- **Interactive UI Dashboard**: Open [http://127.0.0.1:8000/ui](http://127.0.0.1:8000/ui) in any modern browser.
- **REST API Documentation**: Explore OpenAPI Swagger at [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs).
- **Real-time WebSocket Endpoint**: `ws://127.0.0.1:8000/api/v1/telemetry/ws`

---

## 5. Arduino Firmware Integration Workflow

### 5.1 Supplying Your Own Firmware
You do not need to rewrite existing Arduino code to use TwinVolt. To use an existing `.ino` sketch:

1. **Via UI**: Navigate to **Hardware & Arduino** in the sidebar. Click **Upload .ino File** or paste code directly into the integrated Firmware Workspace editor.
2. **Via Filesystem**: Place your sketch in the `firmware/arduino/` directory.

### 5.2 Reference Example Sketch
TwinVolt includes a complete reference sketch at `firmware/arduino/TwinVolt_Arduino_Example.ino`.
This sketch samples analog sensors (or simulated values if sensors are unattached), formats the readings as JSON lines, and transmits them over Serial at 115200 baud.

### 5.3 Supported Serial Wire Protocols

The TwinVolt `ArduinoFrameParser` supports two standard line-delimited formats, as well as automatic format detection (`AUTO`):

#### Format A: JSON Lines (`JSON_LINES`)
Recommended format for flexibility and multi-cell packs:
```json
{"timestamp_ms":1000,"voltage_V":3.725,"current_A":-0.450,"temperature_C":25.3,"cells_V":[3.725]}
```
Supported field names:
- **Voltage**: `voltage_V`, `voltage`, `pack_voltage`, `v_cell`, `v` (Unit: Volts)
- **Current**: `current_A`, `current`, `i_pack`, `i` (Unit: Amperes, positive = discharge, negative = charge)
- **Temperature**: `temperature_C`, `temp_c`, `temperature`, `temp`, `t` (Unit: °C)
- **Cells**: `cells_V`, `cell_voltages`, `cells` (Array of cell voltages in Volts)
- **Timestamp**: `timestamp_ms`, `time_ms`, `millis`, `time` (Milliseconds)

#### Format B: CSV Lines (`CSV`)
Compact format with minimal microcontroller memory overhead:
```csv
1000,3.725,-0.450,25.3
```
Order of columns:
`timestamp_ms,voltage_V,current_A,temperature_C`

#### Diagnostic Filtering
The parser automatically ignores bootloader messages, debug statements, and non-numeric lines (e.g., `"--- Arduino Booting ---"` or `"WiFi connected"`), logging them as diagnostic lines without raising frame errors.

---

## 6. Real-Time Hardware Connection & Upload Workflow

### 6.1 Connecting Hardware
1. Connect your Arduino / ESP32 to the computer via USB.
2. In the TwinVolt dashboard, click **Hardware & Arduino** in the sidebar.
3. Select your serial port from the dropdown (e.g., `COM3`, `COM4` on Windows, or `/dev/ttyUSB0`, `/dev/ttyACM0` on Linux).
4. Select the matching baud rate (default: `115200`).
5. Choose the data format (`Auto Detect`, `JSON Lines`, or `CSV`).
6. Click **Connect to Hardware**.

The status card will update to **CONNECTED**, displaying:
- Live sample rate (Hz)
- Frame count and parse error count
- Last reading timestamp
- Real-time scrolling serial console

### 6.2 Firmware Verification & Flashing
1. **Static Verification**: Click **Verify Sketch** in the Firmware Workspace. The system validates C++/Arduino syntax, ensuring required `setup()`, `loop()`, and `Serial.begin()` definitions are present.
2. **Flashing via Arduino CLI**:
   - If `arduino-cli` is installed locally on your system PATH, you can select your board FQBN (e.g., `arduino:avr:uno`) and flash the board directly through the UI.
   - If `arduino-cli` is not installed, the platform displays instructions to flash using the standard Arduino IDE while keeping the serial monitoring capabilities fully functional.

---

## 7. Isolated Mock Telemetry Generator

For testing the digital twin, UI charts, and fault-detection algorithms without physical hardware, TwinVolt includes a dedicated **Mock Generator**:

1. In the sidebar, select **Mock Generator**.
2. Features:
   - **Start / Stop**: Toggle live synthetic telemetry streaming.
   - **Configurable Parameters**: Base voltage (V), load current (A), temperature (°C), sampling interval (ms), noise amplitude.
   - **Fault Injection**: One-click injection of overvoltage, thermal runaway spikes, under-voltage, or bad frame packets to test safety systems.
   - **Mode Isolation**: Every record emitted by the mock generator is stamped with `source_mode: "MOCK"`. Mock data is strictly isolated from live hardware telemetry and never overwrites real battery states.

---

## 8. REST & WebSocket API Reference

### 8.1 Hardware Gateway Endpoints
- `GET /api/v1/gateway/serial/ports`: Returns list of detected physical COM ports.
- `POST /api/v1/gateway/arduino/connect`: Connects to specified port and baud rate.
- `POST /api/v1/gateway/arduino/disconnect`: Closes the serial connection.
- `GET /api/v1/gateway/arduino/status`: Returns connection state, sample rate, and frame counts.
- `GET /api/v1/gateway/arduino/records`: Retrieves the last N parsed records.

### 8.2 Firmware Workspace Endpoints
- `GET /api/v1/firmware/files`: List sketches in `firmware/arduino/`.
- `GET /api/v1/firmware/files/{filename}`: Download or read sketch source.
- `POST /api/v1/firmware/upload`: Upload an existing `.ino` file.
- `POST /api/v1/firmware/save`: Save edits to an existing sketch.
- `POST /api/v1/firmware/verify`: Run static syntax and structure verification.
- `POST /api/v1/firmware/flash`: Compile and flash sketch via local `arduino-cli`.

### 8.3 Mock Telemetry Endpoints
- `GET /api/v1/mock/status`: Status of synthetic generator.
- `POST /api/v1/mock/start`: Start mock streaming.
- `POST /api/v1/mock/stop`: Stop mock streaming.
- `POST /api/v1/mock/configure`: Update mock parameters and noise levels.
- `POST /api/v1/mock/inject-error`: Inject transient voltage or thermal faults.
- `POST /api/v1/mock/reset`: Reset synthetic battery state.

### 8.4 Real-time WebSocket Protocol
Connect to: `ws://127.0.0.1:8000/api/v1/telemetry/ws`

Payload schema:
```json
{
  "source_id": "arduino-COM3",
  "source_mode": "LIVE",
  "sequence": 142,
  "source_timestamp": 1718000000.123,
  "received_timestamp": 1718000000.125,
  "voltage_V": 3.821,
  "current_A": -0.520,
  "power_W": -1.9869,
  "temperature_C": 26.4,
  "cell_voltages_V": [3.821],
  "soc_pct": 82.5,
  "soh_pct": 98.4,
  "quality": "VALID"
}
```

---

## 9. Hardware Safety & Protection Guidelines

> [!CAUTION]
> **Safety Notice:**
> TwinVolt is an analytics, estimation, and digital twin monitoring platform.
> It is **not** a replacement for hardware-level battery protection.
> 
> The physical Battery Management System (BMS) must maintain independent hardware overvoltage, undervoltage, overcurrent, and thermal cutoff protections. Do not bypass or disable BMS protection circuits when interfacing with TwinVolt.

---

## 10. Automated Testing

Run the full automated test suite:
```bash
python -m pytest
```

Run hardware gateway and mock tests specifically:
```bash
python -m pytest tests/unit/gateway/test_arduino_frame_parser.py
python -m pytest tests/unit/gateway/test_arduino_connection_manager.py
python -m pytest tests/unit/services/test_mock_service.py
python -m pytest tests/unit/api/test_hardware_and_firmware_api.py
```
All 891 platform tests pass deterministically without requiring physical hardware.
