# TWINVOLT UI REDESIGN BASELINE & AUDIT REPORT

**Date:** 2026-10-30
**Phase:** Stage 0 — Pre-Modification Codebase Audit
**Status:** Baseline Established (928/928 tests passing, JS syntax 21/21 clean)

---

## 1. System Overview & Architecture

TwinVolt is a universal, battery-agnostic cyber-physical digital twin platform. It provides real-time telemetry ingestion, physics-based equivalent circuit battery modelling (ECM), Kalman-filter state estimation (SoC/SoH), hardware gateway connectivity (Web Serial, Web Bluetooth, Arduino, Edge TCP/UDP), synthetic telemetry generation with fault injection, benchmark validation, and explainable diagnostics.

### Deployment & Serving Architecture
- **Runtime Host:** Unified FastAPI ASGI application served locally via Uvicorn and on Vercel Serverless via `@vercel/python` through `api/index.py`.
- **Static Asset Mounts:** `src/api/app.py` resolves `src/ui` and mounts:
  - `/` & `/index.html` → `src/ui/index.html`
  - `/css` → `src/ui/css`
  - `/js` → `src/ui/js`
  - `/assets` → `src/ui/assets`
  - `/ui` → `src/ui`
  - SPA Fallbacks: `/overview`, `/telemetry`, `/hardware`, `/mock`, `/twin`, `/estimation`, `/replay`, `/events`, `/diagnostics`, `/benchmarking`, `/datasets` all map cleanly to `index.html`.
- **Vercel Specification:** `vercel.json` maps builds to `api/index.py` using `@vercel/python` and catch-all routes `/(.*)` to `api/index.py`.

---

## 2. Existing Frontend Inventory

### 2.1 Navigation & Shell Structure (`src/ui/index.html`)
The main application shell (`#app-shell`) consists of:
1. **Header (`#app-header`):**
   - Brand logo (`.brand-logo`), title (`.brand-title`), and version tag (`#header-version`).
   - Twin selector (`#header-twin-select`).
   - Mode badge (`#header-mode-badge`, `#header-mode-text`).
   - Latency indicator (`#latency-readout`, `#header-latency`).
   - WebSocket connection status badge (`#header-ws-status`).
2. **Sidebar (`#app-sidebar`):**
   - 11 navigation buttons with `data-view` attributes:
     - `overview` (Overview)
     - `telemetry` (Live Telemetry)
     - `hardware` (Hardware & Arduino)
     - `mock` (Mock Generator)
     - `twin` (Digital Twin)
     - `estimation` (Estimation)
     - `replay` (Replay & Eval)
     - `events` (Event Log)
     - `diagnostics` (Diagnostics)
     - `benchmarking` (Benchmarking)
     - `datasets` (Dataset Lab)
   - Sidebar footer branding.
3. **Main Viewport (`#app-main`):**
   - 11 view containers:
     - `#view-overview` (`.view-container.active`)
     - `#view-telemetry` (`.view-container`)
     - `#view-hardware` (`.view-container`)
     - `#view-mock` (`.view-container`)
     - `#view-twin` (`.view-container`)
     - `#view-estimation` (`.view-container`)
     - `#view-replay` (`.view-container`)
     - `#view-events` (`.view-container`)
     - `#view-diagnostics` (`.view-container`)
     - `#view-benchmarking` (`.view-container`)
     - `#view-datasets` (`.view-container`)

### 2.2 JavaScript Architecture (`src/ui/js/`)
- `app.js`: Main bootstrapper, mounts view controllers, coordinates navigation switching, twin selection, and state subscription.
- `api.js`: REST client, dynamically resolves API & WebSocket base URLs.
- `state.js`: Central pub/sub store (`AppStore`).
- `websocket.js`: Resilient WebSocket client with automatic reconnection and exponential backoff.
- `serial.js`: Browser Web Serial API connection manager for direct USB Arduino connection.
- `ble.js`: Browser Web Bluetooth API connection manager for BLE battery sensors.
- `charts.js`: Canvas-based real-time telemetry line charts.
- `telemetry_pipeline.js`: Client-side telemetry stream normalizer and buffer.
- `config.js`: Runtime URL injection bridge.
- `html.js`: Sanitized HTML template tag helpers.
- `views/`: 11 view controllers managing DOM rendering and interaction hooks.

---

## 3. Protected Functional Contracts & DOM Hooks

Every view relies on specific DOM element IDs and classes. These MUST be preserved:

| View | Critical DOM IDs / Functional Hooks | Functional Purpose |
|---|---|---|
| **Header** | `#header-twin-select`, `#header-mode-badge`, `#header-mode-text`, `#header-latency`, `#header-ws-status`, `#header-version` | Twin switching, telemetry stream state, latency display |
| **Overview** | `#overview-btn-test-sample`, `LIVE HARDWARE SENSORS`, `#overview-soc-gauge`, `#overview-soh-gauge`, metric displays | Quick test sample injection, live sensor strip, high-level metrics |
| **Telemetry** | `#telem-voltage-chart`, `#telem-current-chart`, `#telem-temp-chart`, filter controls, live stream table | High-rate real-time telemetry canvas charts and tables |
| **Hardware** | `#btn-connect-serial`, `#btn-connect-ble`, `#serial-baud-rate`, `#hardware-status-banner`, `#raw-serial-feed` | Web Serial & Web Bluetooth browser connection controls |
| **Mock** | `#mock-waveform-select`, `#mock-profile-select`, `#btn-start-mock`, `#btn-stop-mock`, fault injection triggers | Synthetic telemetry generation with fault modes |
| **Twin** | `#twin-model-select`, `#twin-rc-pairs`, parameter adjustment sliders/inputs | Equivalent circuit model (1RC/2RC) tuning |
| **Estimation** | `#est-soc-kf`, `#est-soc-cc`, `#est-soh-metric`, algorithm comparison readouts | EKF vs. Coulomb Counting state estimation metrics |
| **Replay** | `#replay-dataset-select`, `#btn-play-pause`, `#btn-step`, scrub bar | Replay of recorded battery cycle sessions |
| **Events** | `#events-filter-severity`, `#events-table-body`, `#btn-clear-events` | Domain lifecycle, warning, and fault events log |
| **Diagnostics** | `#diag-active-hypotheses`, `#diag-evidence-list`, `#diag-explanation-card` | Explainable Bayesian diagnostic reasoning engine |
| **Benchmarking** | `#btn-run-benchmark`, `#btn-reset-benchmarks`, `#bench-dataset-select`, `#bench-gating-badge` | Ground-truth benchmark evaluation matrix |
| **Dataset Lab** | `#dataset-dropzone`, `#dataset-file`, `#dataset-refresh`, `#dataset-list` | CSV/JSON battery drive-cycle dataset management |

---

## 4. Protected Engineering Codebase (DO NOT MODIFY)

The following directories and files contain core engineering, physics, mathematics, and operational logic that are strictly protected from modification:
- `src/domain/` (Entities, value objects, physics enums, validation invariants)
- `src/models/` (Equivalent circuit models, OCV-SoC curves, thermal models)
- `src/estimators/` (Extended Kalman Filter, Coulomb Counter, SoH estimation)
- `src/diagnostics/` (Bayesian inference, temporal evidence, hypotheses)
- `src/benchmarking/` (Alignment, metric calculation, stratification)
- `src/prognostics/` (Remaining useful life, trajectory prediction, degradation)
- `src/gateway/` (Serial frame parsing, Arduino protocol, daemon management)
- `src/runtime/` (Digital twin synchronizer, anomaly detection)
- `src/services/` (Mock telemetry service, twin service, pack service)
- `src/api/routes/` (FastAPI route endpoints, request/response schemas)
- `src/api/websocket/` (WebSocket connection manager, benchmark events)
- `api/index.py` & `vercel.json` (Vercel serverless deployment specifications)
- `firmware/` (Arduino sketch and embedded C++ code)

---

## 5. Safe Files for Presentation Transformation

The following presentation assets and files are designated for styling, visual enhancement, and additive presentation:
1. `src/ui/css/variables.css` (Update design tokens to Luxury Engineering light palette: `#F7F9FC`, `#FFFFFF`, `#14243A`, `#1769D2`, `#3188F5`, `#12A9C7`, `#E2E8F0`, `#15966B`, `#D99525`, `#D84C4C`).
2. `src/ui/css/layout.css` (Header, sidebar, navigation, content spacing, responsive containers).
3. `src/ui/css/components.css` (Cards, buttons, metrics, tables, badges, modals, dropzones).
4. `src/ui/css/charts.css` (Clean white chart canvases, tooltips, engineering legends).
5. `src/ui/css/landing.css` *(New file)*: Dedicated styles for the additive landing page.
6. `src/ui/js/landing.js` *(New file)*: Dedicated interactive logic for the landing page (3D canvas battery visualizer, interactive specs, smooth scroll, dashboard launch).
7. `src/ui/landing.html` *(New file)* or additive landing mode within `src/ui/index.html` / `app.py`.
8. `src/ui/index.html` (Additive header/navigation tweaks, linking to landing page, preserving all 11 view containers).

---

## 6. Baseline Test Verification

- **Command:** `.venv\Scripts\python.exe -m pytest tests\`
- **Result:** **928 passed, 1 warning (deprecation notice for starlette testclient) in 19.93s**.
- **JavaScript Syntax Validation:** `node --check` across all 21 JavaScript files in `src/ui/js/` and `src/ui/js/views/` → **21/21 passed with zero errors**.
- **Git Status:** Working tree clean (`main` at commit `0b9c1e3`).
