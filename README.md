# TwinVolt — Universal Battery Digital Twin Platform

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Development Status](https://img.shields.io/badge/Status-Active%20Development-green.svg)](#current-development-status)
[![Tests](https://img.shields.io/badge/Tests-891%20Passing-brightgreen.svg)](#testing-philosophy)

---

## 1. Project Overview

**TwinVolt** is a modern, modular, and universal **Battery Digital Twin Platform** designed to model, monitor, simulate, and predict the behavior of electrochemical energy storage systems.

TwinVolt builds a dynamic, high-fidelity virtual replica of battery packs across diverse chemistries, form factors, and applications—bridging the gap between physical battery hardware, electro-thermal modeling, state estimation, and cloud analytics.

---

## 2. Project Vision

Modern battery systems operate across diverse domains: electric vehicles, microgrids, grid-scale BESS, aerospace, robotics, and consumer electronics. However, existing battery tooling is frequently fragmented—tightly coupled to proprietary BMS hardware, locked into single cell chemistries, or isolated within theoretical simulation packages.

**TwinVolt's vision** is to deliver an open, universal, and production-grade Digital Twin foundation that unifies:
- **Real-time telemetry ingestion** from physical battery management systems (BMS),
- **Physics-based, equivalent circuit (ECM), and data-driven battery models**,
- **High-accuracy state estimation** (State of Charge [SOC], State of Health [SOH], State of Power [SOP], and Remaining Useful Life [RUL]),
- **Continuous parameter identification, fault detection, and thermal anomaly forecasting**,
- **Universal deployment across hardware and virtual/simulated environments.**

---

## 3. Core Architectural Philosophy

TwinVolt is engineered from the ground up on ten foundational design principles:

1. **Battery Agnostic**: Supports any cell chemistry (NMC, LFP, LCO, NCA, LTO, Solid-State, Sodium-ion), form factor (cylindrical, pouch, prismatic), and pack configuration via parametric configuration.
2. **Model Agnostic**: Supports Equivalent Circuit Models (Thevenin, 2-RC), electrochemical physics models (PyBaMM/DFN/SPM), and neural/empirical models behind a unified interface.
3. **Hardware Agnostic**: Independent of any specific BMS microcontroller, analog front-end (AFE), or hardware vendor.
4. **Protocol Agnostic**: Ingests telemetry across MQTT, CAN bus, Modbus, BLE, Serial/UART, WebSocket, REST using pluggable adapters.
5. **Modular Architecture**: Clear boundary layers and dependency inversion.
6. **Separation of Concerns**: Strict isolation between ingestion, domain modeling, state estimation, persistence, and visualization.
7. **Dual Battery Support (Physical + Virtual)**: Live hardware telemetry, historical replay, or synthetic load profiles.
8. **High Testability**: Every layer architected for rigorous automated testing.
9. **Extensibility**: Standardized plugin points for custom estimators, adapters, and analytics.
10. **Future Scalability**: Designed from single-cell testbenches to distributed multi-pack fleet monitoring.

---

## 4. Current Development Status

> [!IMPORTANT]
> **TwinVolt is in active development.** Core domain, estimation, ingestion, digital twin runtime, and API layers are implemented. Hardware gateway, mock telemetry generator, and the full real-time monitoring dashboard have been integrated.

| Layer / Feature Area | Status |
| :--- | :--- |
| **Repository Structure & Docs** | ✅ Established |
| **Domain Entities & Canonical Schema** | ✅ Implemented |
| **Battery Model Abstraction & ECM Engines** | ✅ Implemented |
| **State Estimation (SOC / SOH / SOP)** | ✅ Implemented (EKF, Coulomb Counting, SOH) |
| **Data Acquisition & Protocol Adapters** | ✅ Implemented (TCP, UDP, CAN, Serial, CSV, JSON) |
| **Digital Twin Core Engine** | ✅ Implemented |
| **Backend Data Platform & APIs (FastAPI)** | ✅ Implemented |
| **Arduino / USB Serial Hardware Gateway** | ✅ Implemented (JSON Lines, CSV, Auto-detect) |
| **Isolated Mock Telemetry Generator** | ✅ Implemented (with fault injection) |
| **Firmware Workspace & Verification** | ✅ Implemented |
| **Real-Time WebSocket Telemetry** | ✅ Implemented |
| **Frontend Dashboard & Monitoring UI** | ✅ Implemented |
| **Dataset Lab & Replay** | ✅ Implemented |
| **Benchmarking & Prognostics** | ✅ Implemented |
| **Automated Test Suite (891 tests)** | ✅ All Passing |

---

## 5. Quick Start

### Prerequisites
- Python 3.11+
- pip

### Setup

```bash
# 1. Clone the repository
git clone https://github.com/Prashant110405/TwinVolt-Battery-Digital-Twin.git
cd TwinVolt-Battery-Digital-Twin

# 2. (Recommended) Create and activate a virtual environment
python -m venv .venv
# Windows PowerShell:
.venv\Scripts\Activate.ps1
# macOS / Linux:
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env

# 5. Start the server
python -m src.server --host 127.0.0.1 --port 8000
```

Open your browser to **[http://127.0.0.1:8000/ui](http://127.0.0.1:8000/ui)**.

- **API Docs**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- **WebSocket**: `ws://127.0.0.1:8000/api/v1/telemetry/ws`

### Run Automated Tests
```bash
python -m pytest
```
All **891 tests** pass without requiring physical hardware.

---

## 6. High-Level Architecture

```text
┌─────────────────────────────────────────────────────────────────────────┐
│                    Physical / Virtual Data Sources                      │
│   (BMS Hardware, CAN Loggers, Arduino/ESP32, Laboratory Cyclers)        │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    Data Acquisition / Adapter Layer                     │
│    (Arduino Serial Gateway, CAN Bus, TCP/UDP, Replay Handlers)          │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         Canonical Telemetry                             │
│       (Normalized Timestamps, Pack/Cell Voltages, Currents, Temps)      │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│           State Estimation / Analytics / Fault Detection                │
│       (EKF SOC, SOH Capacity Fade, Thermal Anomaly Alerts, RUL)         │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     Backend / Data Platform                             │
│     (FastAPI Services, REST API, WebSocket Real-Time Streams)           │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     Frontend / Visualization                            │
│     (Real-Time Dashboard, Hardware Page, Mock Generator, Charts)        │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 7. Dashboard Features

### Live Telemetry Dashboard (`/ui`)
- **Connection status panel** with heartbeat and stale-data detection.
- **Data source and mode indicator** — `LIVE` hardware vs. `MOCK`.
- **Voltage (V), Current (A), Power (W = V × I), Temperature (°C)**.
- **SOC (%)** and **SOH (%)** from validated EKF and Coulomb-counting estimators.
- **Cell-wise voltage** panel when individual cell readings are available.
- **Historical time-series charts** with configurable time ranges.
- **Telemetry event timeline** with data-quality badges.
- **JSON / CSV telemetry export** for offline analysis.

### Hardware & Arduino Page
Navigate to **Hardware & Arduino** in the sidebar:
- **Firmware Workspace**: Upload, view, edit, and verify `.ino` sketches.
- **Board Configuration**: Port selector, baud rate, data format, sensor mappings.
- **Live Serial Console**: Scrolling real-time incoming bytes and parsed records.
- **Connection Metrics**: Frames received, parse errors, sample rate, last-valid timestamp.
- **Firmware Flash** (requires local `arduino-cli`): Explicit user-initiated compile + upload.

### Mock Generator Page
Navigate to **Mock Generator** in the sidebar:
- **Isolated synthetic telemetry** — never mixed with live hardware data.
- **Configurable parameters**: Voltage range, current, temperature, sample interval, noise.
- **Fault injection**: Overvoltage spike, thermal runaway, under-voltage, bad frame.
- **Deterministic seed** support for repeatable automated testing.
- **Clear MOCK badge** visible at all times when active.

---

## 8. Arduino Hardware Integration

For full setup instructions, see [docs/hardware-and-arduino-integration.md](docs/hardware-and-arduino-integration.md).

**Workflow summary:**
1. Connect your Arduino / ESP32 to the computer via USB.
2. Open the Hardware page in the TwinVolt dashboard.
3. Select your serial port (e.g., `COM3` on Windows, `/dev/ttyUSB0` on Linux).
4. Select baud rate (`115200`).
5. Choose data format (`Auto`, `JSON Lines`, or `CSV`).
6. Click **Connect** — live telemetry flows through the digital twin pipeline.

**Supported serial formats:**

JSON Lines (recommended):
```json
{"timestamp_ms":1000,"voltage_V":3.725,"current_A":-0.45,"temperature_C":25.3}
```

CSV (compact):
```
1000,3.725,-0.450,25.3
```

A reference firmware sketch is available at `firmware/arduino/TwinVolt_Arduino_Example.ino`.

> [!NOTE]
> **Serial Port Boundary**: A remotely hosted web server cannot directly access a USB serial port on a client's local machine. The TwinVolt backend **must run locally** on the machine physically connected to the Arduino.

---

## 9. Repository Structure

```text
TwinVolt-Battery-Digital-Twin/
│
├── README.md
├── LICENSE
├── .gitignore
├── .env.example                # Environment configuration template
├── requirements.txt            # Python dependencies
│
├── firmware/
│   └── arduino/
│       ├── README.md                       # Protocol specification
│       ├── TwinVolt_Arduino_Example.ino    # Reference sketch
│       └── protocol_examples/              # JSON Lines and CSV traces
│
├── docs/
│   ├── hardware-and-arduino-integration.md # Hardware setup guide
│   ├── configuration.md
│   ├── testing-strategy.md
│   └── ...
│
├── src/
│   ├── api/
│   │   └── routes/
│   │       ├── gateway.py      # Hardware connection endpoints
│   │       ├── firmware.py     # Firmware workspace endpoints
│   │       ├── mock.py         # Mock generator endpoints
│   │       └── ...
│   ├── gateway/
│   │   └── arduino/            # USB serial gateway module
│   │       ├── models.py
│   │       ├── frame_parser.py
│   │       ├── serial_transport.py
│   │       └── connection_manager.py
│   ├── services/
│   │   ├── mock_service.py     # Isolated mock telemetry generator
│   │   ├── telemetry_service.py
│   │   └── ...
│   ├── domain/                 # Battery domain models
│   ├── models/                 # Physics and ECM models
│   └── ui/                     # Frontend dashboard
│       ├── index.html
│       ├── css/
│       └── js/views/
│           ├── hardware.js
│           ├── mock.js
│           └── telemetry.js
│
└── tests/
    └── unit/
        ├── gateway/
        │   ├── test_arduino_frame_parser.py        # 8 tests
        │   └── test_arduino_connection_manager.py  # 2 tests
        ├── services/
        │   └── test_mock_service.py                # 3 tests
        └── api/
            └── test_hardware_and_firmware_api.py   # 7 tests
```

---

## 10. Key API Endpoints

| Endpoint | Description |
| :--- | :--- |
| `GET /api/v1/gateway/serial/ports` | List detected COM ports |
| `POST /api/v1/gateway/arduino/connect` | Connect to serial port |
| `POST /api/v1/gateway/arduino/disconnect` | Disconnect |
| `GET /api/v1/gateway/arduino/status` | Connection state and metrics |
| `GET /api/v1/firmware/files` | List firmware workspace sketches |
| `POST /api/v1/firmware/upload` | Upload `.ino` file |
| `POST /api/v1/firmware/verify` | Static syntax verification |
| `POST /api/v1/firmware/flash` | Flash via arduino-cli |
| `GET /api/v1/mock/status` | Mock generator status |
| `POST /api/v1/mock/start` | Start mock streaming |
| `POST /api/v1/mock/stop` | Stop mock streaming |
| `POST /api/v1/mock/inject-error` | Inject fault conditions |

WebSocket: `ws://127.0.0.1:8000/api/v1/telemetry/ws`

---

## 11. Security Considerations

> [!WARNING]
> TwinVolt is designed for **local development and trusted lab networks**. Before exposing to untrusted networks:
> - Enable authentication and HTTPS.
> - Restrict CORS origins in `src/api/app.py`.
> - Do not expose serial port or administrative endpoints publicly.
> - Uploaded `.ino` files are treated as untrusted source text only; they are never executed directly.

---

## 12. Testing Philosophy

- **Unit Testing**: Mathematical algorithms, OCV-SOC tables, schema validators.
- **Integration Testing**: Telemetry ingestion, API endpoints, WebSocket streams.
- **Fault Injection**: Malformed frames, NaN values, disconnections, stale data.
- **Synthetic Simulation**: Drive-cycle and CCCV profile verification.

**Total tests: 891 | All passing | No physical hardware required.**

---

## 13. Hardware Safety Notice

> [!CAUTION]
> TwinVolt is an analytics and digital twin monitoring platform.
> It is **not** a replacement for hardware-level battery protection.
> The physical BMS must maintain independent overvoltage, undervoltage, overcurrent, and thermal cutoff protections. Do not bypass hardware protection circuits when interfacing with TwinVolt.

---

## 14. License

This project is licensed under the **MIT License** — see the [LICENSE](LICENSE) file for details.
