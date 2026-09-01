# TwinVolt — Source Code (`src/`)

This directory will house all production source code for the **TwinVolt Universal Battery Digital Twin Platform**.

---

## Architecture Overview

Production code in `src/` will be strictly organized according to the approved layered, modular, and dependency-inverted TwinVolt architecture:

```text
Physical/Virtual Data Sources
        ↓
Data Acquisition / Adapter Layer
        ↓
Canonical Telemetry
        ↓
Universal Battery Domain
        ↓
Battery Model Abstraction
        ↓
Digital Twin Core
        ↓
State Estimation / Analytics / Fault Detection / Prediction
        ↓
Backend / Data Platform
        ↓
Frontend / Visualization
```

---

## Planned Source Layout

When implemented across upcoming project milestones, the production codebase will be structured into distinct, decoupled modules:

1. **`adapters/` (Data Acquisition & Ingestion Layer)**
   - Ingestion adapters for diverse protocols (MQTT, CAN, Serial/UART, Modbus, BLE, WebSocket).
   - Replay adapters for historical datasets and synthetic profile injectors.
   - Translation of raw physical/network payloads into canonical telemetry format.

2. **`telemetry/` (Canonical Telemetry & Data Processing)**
   - Strongly-typed canonical telemetry models and validation schemas.
   - Real-time stream sanitization, unit normalization, and validation rules.

3. **`domain/` (Universal Battery Domain Entities)**
   - Battery pack, module, and cell configuration definitions.
   - Chemistry parameter profiles (NMC, LFP, LCO, etc.).
   - Physical constraints, operational boundaries, and thermal limits.

4. **`models/` (Battery Model Abstraction Layer)**
   - Common interface for battery mathematical models.
   - Equivalent Circuit Models (ECM 1-RC, 2-RC).
   - Electrochemical model wrappers (e.g., PyBaMM DFN/SPM integration).
   - Thermal dynamics models and look-up table (OCV-SOC) managers.

5. **`core/` (Digital Twin Engine)**
   - State synchronization between physical telemetry and virtual models.
   - Simulation coordination and co-simulation execution loops.
   - Parameter tracking and model state updates.

6. **`estimation/` & `analytics/` (State Estimation & Intelligence)**
   - State of Charge (SOC) estimators (Coulomb Counting, EKF, UKF).
   - State of Health (SOH) tracking (capacity degradation, internal resistance growth).
   - State of Power (SOP) dynamic limits calculation.
   - Anomaly detection, cell imbalance alerts, and Remaining Useful Life (RUL) prediction.

7. **`api/` & `services/` (Backend Platform & Data Storage)**
   - FastAPI REST and WebSocket endpoints for twin control and telemetry streaming.
   - Database persistence layers (TimescaleDB / PostgreSQL time-series storage, Redis caching).

8. **`ui/` (Frontend Visualization Application)**
   - Modern web dashboard for pack metrics, cell heatmaps, state estimation curves, and 3D pack visualizations.

---

## Implementation Status

> [!NOTE]
> No application packages or placeholder Python classes have been created yet. Packages will be introduced incrementally and cleanly in accordance with project milestones.
