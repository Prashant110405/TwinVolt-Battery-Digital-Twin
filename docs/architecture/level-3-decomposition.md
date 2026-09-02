# TwinVolt — Level 3 Architecture Decomposition & Engineering Plan

[![Architecture: Level 3](https://img.shields.io/badge/Architecture-Level%203%20Runtime%20%26%20Ingestion-blue.svg)](#)
[![Status: Proposed Plan](https://img.shields.io/badge/Status-Proposed%20Plan-yellow.svg)](#)

---

## Executive Summary

This document establishes the formal engineering decomposition, architectural boundaries, dependency graph, and subtask specifications for **Level 3 — Ingestion, State Engine & Real-Time Synchronization Layer** of the **TwinVolt Universal Battery Digital Twin Platform**.

Level 3 delivers the runtime execution core and data ingestion pipeline that bridges live physical battery telemetry with the locked Level 2 physical and mathematical modeling core:
- **Universal Telemetry Ingestion Pipeline**: Protocol-agnostic adapters (JSON, CSV, Serial/BMS frames, Synthetic generators) transforming external payloads into canonical `TelemetrySnapshot` value objects.
- **Digital Twin Runtime Core (`DigitalTwinInstance`)**: State coordinator binding a `BatteryPack` domain entity, `BatteryModel` simulation core, and `StateEstimator` into a synchronized live digital twin.
- **Dual-Track Real-Time Synchronization**: Simultaneous tracking of measured BMS observations vs. model-predicted dynamics, generating instantaneous residuals ($\tilde{V} = V_{meas} - V_{sim}$, $\tilde{T} = T_{meas} - T_{sim}$) and virtual sensor telemetry.
- **Physics-Informed Anomaly Detection**: Real-time residual monitoring detecting sensor drift, internal short-circuit pre-cursors, thermal runaway precursors, and abnormal impedance growth.
- **Decoupled Event Bus & Observability**: Thread-safe in-process publish-subscribe event system dispatching state updates, anomalies, and health transitions to registered observers.
- **Time-Series Persistence Repositories**: Pluggable storage abstraction (In-memory circular buffer, file append-only storage) with zero database coupling.
- **Dataset & Drive-Cycle Replay Engine**: Deterministic offline simulation runner for standard automotive/grid drive cycles (WLTP, US06, pulse discharge) with automated tracking error evaluation (RMSE, MAE).

```mermaid
flowchart TD
    subgraph Level 1 & 2 Foundations [Locked Level 1 & Level 2 Foundation]
        L1_DOM[src/domain/]
        L1_TEL[src/telemetry/]
        L2_MOD[src/models/ - ECM / Physics / Pack]
        L2_EST[src/estimators/ - EKF / SOH / CC]
    end

    subgraph Level 3 Ingestion & Runtime Layer
        T31[3.1: Ingestion Pipeline & Protocol Adapters]
        T32[3.2: Storage Repositories & Buffer Engine]
        T33[3.3: Event Bus & Observability Engine]
        T34[3.4: Digital Twin Runtime Core & Synchronizer]
        T35[3.5: Drive Cycle Replay & Metrics Evaluator]
        T36[3.6: Level 3 Integration & Gate Review]
    end

    Level 1 & 2 Foundations --> T31
    Level 1 & 2 Foundations --> T34
    T31 --> T34
    T34 --> T32
    T34 --> T33
    T34 --> T35
    T31 --> T36
    T32 --> T36
    T33 --> T36
    T34 --> T36
    T35 --> T36
```

---

## 1. Architectural Boundaries & Principles

1. **Strict Consumption of Locked Layers**: Level 3 consumes Level 1 (`src/domain/`, `src/telemetry/`, `src/schemas/`) and Level 2 (`src/models/`, `src/estimators/`) strictly through their established public interfaces and protocols (`BatteryModel`, `StateEstimator`, `TelemetrySnapshot`, `BatteryPack`). Zero modifications or monkey-patching of Level 0–2 code.
2. **Protocol & Transport Independence**: Ingestion logic is decoupled from transport drivers. Protocol adapters convert raw payloads into canonical `TelemetrySnapshot` instances before the runtime engine processes them.
3. **Synchronized Dual-Track Co-Simulation**:
   - **Track 1 (Observed Reality)**: Actual measurements from BMS and physical sensors.
   - **Track 2 (Digital Twin Reality)**: Co-simulated electro-thermal state advancing in lockstep with measured load current $I(t)$ and ambient temperature $T_{amb}(t)$.
   - **Residuals & Discrepancy Diagnostics**: $\Delta V(t) = V_{meas}(t) - V_{sim}(t)$ and $\Delta T(t) = T_{meas}(t) - T_{sim}(t)$ provide early warning indicators for cell degradation or anomalous divergence.
4. **Non-Blocking & Zero Silent Fallback**: Ingestion validation immediately flags malformed, non-monotonic, or out-of-bounds telemetry with explicit quality codes (`INVALID`, `DEGRADED`, `STALE`) rather than guessing missing values.
5. **No Premature Level 4/5 Coupling**: Zero REST APIs (FastAPI), WebSocket network servers, external databases (PostgreSQL/TimescaleDB), MQTT network daemons, or UI dashboards will be introduced in Level 3. Storage and transport remain purely interface-driven.

---

## 2. Subtask Breakdown

### Subtask 3.1 — Ingestion Pipeline & Protocol Adapters
- **Purpose**: Implement a robust, protocol-agnostic ingestion pipeline capable of parsing, validating, rate-limiting, and converting external telemetry payloads into canonical `TelemetrySnapshot` instances.
- **Inputs**: Raw byte frames, JSON strings, CSV rows, dictionary payloads.
- **Outputs**: `IngestionPipeline`, `IngestionResult`, `JSONTelemetryAdapter`, `CSVTelemetryAdapter`, `SyntheticTelemetryAdapter`, `SerialFrameTelemetryAdapter`.
- **Expected Files**:
  - `src/ingestion/__init__.py`
  - `src/ingestion/base.py`
  - `src/ingestion/pipeline.py`
  - `src/ingestion/validation.py`
  - `src/ingestion/exceptions.py`
  - `src/ingestion/adapters/__init__.py`
  - `src/ingestion/adapters/json_adapter.py`
  - `src/ingestion/adapters/csv_adapter.py`
  - `src/ingestion/adapters/synthetic_adapter.py`
  - `src/ingestion/adapters/serial_frame_adapter.py`
  - `tests/unit/ingestion/test_pipeline.py`
  - `tests/unit/ingestion/test_json_adapter.py`
  - `tests/unit/ingestion/test_csv_adapter.py`
  - `tests/unit/ingestion/test_synthetic_adapter.py`
- **Dependencies**: Level 1 Telemetry (`src/telemetry/`).

---

### Subtask 3.2 — Time-Series Persistence & Storage Repositories
- **Purpose**: Implement storage repository abstractions for telemetry snapshots, state history vectors, and events with in-memory bounded circular buffers and file append-only serialization.
- **Inputs**: `TelemetrySnapshot`, `EstimationState`, `ModelState`, `TwinEvent`.
- **Outputs**: `TelemetryRepository`, `StateHistoryRepository`, `EventRepository`, `InMemoryCircularBufferRepository`, `FileAppendRepository`.
- **Expected Files**:
  - `src/storage/__init__.py`
  - `src/storage/base.py`
  - `src/storage/memory_repository.py`
  - `src/storage/file_repository.py`
  - `src/storage/exceptions.py`
  - `tests/unit/storage/test_memory_repository.py`
  - `tests/unit/storage/test_file_repository.py`
- **Dependencies**: Level 1 & 2 types.

---

### Subtask 3.3 — Internal Event Bus & Observability Engine
- **Purpose**: Implement an asynchronous/synchronous in-process publish-subscribe event bus to broadcast telemetry events, state updates, threshold alerts, and health degradation transitions.
- **Inputs**: Event payloads and typed subscriber callables.
- **Outputs**: `DigitalTwinEventBus`, domain event types (`TelemetryReceivedEvent`, `TwinSynchronizedEvent`, `AnomalyDetectedEvent`, `ThermalAlertEvent`), subscriber registry with error isolation.
- **Expected Files**:
  - `src/events/__init__.py`
  - `src/events/base.py`
  - `src/events/bus.py`
  - `src/events/types.py`
  - `src/events/handlers.py`
  - `tests/unit/events/test_event_bus.py`
- **Dependencies**: Level 1 Domain.

---

### Subtask 3.4 — Digital Twin Runtime Core & Real-Time Synchronizer
- **Purpose**: Build the central `DigitalTwinInstance` that binds a physical `BatteryPack`, simulation model (`BatteryModel`), and state estimator (`StateEstimator`), executing dual-track co-simulation, residual tracking, and anomaly detection.
- **Inputs**: `BatteryPack`, `BatteryModel`, `StateEstimator`, canonical `TelemetrySnapshot`.
- **Outputs**: `DigitalTwinInstance`, `RuntimeConfig`, `TwinSynchronizer`, `TwinSyncOutput`, `PhysicsAnomalyDetector`.
- **Expected Files**:
  - `src/runtime/__init__.py`
  - `src/runtime/config.py`
  - `src/runtime/instance.py`
  - `src/runtime/synchronizer.py`
  - `src/runtime/anomaly_detector.py`
  - `src/runtime/exceptions.py`
  - `tests/unit/runtime/test_digital_twin_instance.py`
  - `tests/unit/runtime/test_synchronizer.py`
  - `tests/unit/runtime/test_anomaly_detector.py`
- **Dependencies**: Subtasks 3.1, 3.2, 3.3, Level 2 Models & Estimators.

---

### Subtask 3.5 — Drive-Cycle Replay & Tracking Evaluator
- **Purpose**: Implement a deterministic drive-cycle runner for simulating and replaying standard automotive/grid profiles (WLTP, US06, constant discharge/charge) with automated performance and tracking error metrics ($\text{RMSE}$, $\text{MAE}$, $\text{Max Error}$, $R^2$).
- **Inputs**: Time-series current profiles, initial conditions, model instances.
- **Outputs**: `DriveCycleReplayEngine`, `ReplayResult`, `TrackingMetricsEvaluator`.
- **Expected Files**:
  - `src/replay/__init__.py`
  - `src/replay/engine.py`
  - `src/replay/evaluator.py`
  - `src/replay/profiles.py`
  - `tests/unit/replay/test_replay_engine.py`
  - `tests/unit/replay/test_evaluator.py`
- **Dependencies**: Subtasks 3.1, 3.4.

---

### Subtask 3.6 — Level 3 System Integration & Gate Review
- **Purpose**: Execute end-to-end integration tests connecting live ingestion $\rightarrow$ runtime dual-track co-simulation $\rightarrow$ residual generation $\rightarrow$ event dispatch $\rightarrow$ storage persistence, culminating in the formal Level 3 Gate Report (`docs/runtime-validation.md`).
- **Inputs**: Full Level 3 codebase and test suites.
- **Outputs**: `tests/integration/test_level3_end_to_end.py`, `docs/runtime-validation.md`.
- **Dependencies**: Subtasks 3.1 through 3.5.

---

## 3. Implementation Sequence

```text
┌────────────────────────────────────────────────────────────────────────┐
│ Subtask 3.1: Ingestion Pipeline & Protocol Adapters                    │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
         ┌──────────────────────────┴──────────────────────────┐
         ▼                                                     ▼
┌─────────────────────────────────────┐       ┌─────────────────────────────────────┐
│ Subtask 3.2: Storage Repositories   │       │ Subtask 3.3: Event Bus Engine       │
└──────────────────┬──────────────────┘       └──────────────────┬──────────────────┘
                   │                                             │
                   └──────────────────────────┬──────────────────┘
                                              ▼
┌────────────────────────────────────────────────────────────────────────┐
│ Subtask 3.4: Digital Twin Runtime Core & Synchronizer                  │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ Subtask 3.5: Drive-Cycle Replay & Tracking Evaluator                   │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ Subtask 3.6: Level 3 Integration & Gate Review                         │
└────────────────────────────────────────────────────────────────────────┘
```
