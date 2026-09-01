# TwinVolt — Level 2 Architecture Decomposition & Engineering Plan

[![Architecture: Level 2](https://img.shields.io/badge/Architecture-Level%202%20Modeling%20%26%20Estimation-blue.svg)](#)
[![Status: Approved Plan](https://img.shields.io/badge/Status-Approved%20Decomposition-green.svg)](#)

---

## Executive Summary

This document establishes the formal engineering decomposition, architectural boundaries, dependency graph, and subtask specifications for **Level 2 — Battery Modeling & Physical/Mathematical Layer** of the **TwinVolt Universal Battery Digital Twin Platform**.

Level 2 delivers the mathematical and physical core of the digital twin:
- **Pluggable Model Architecture**: Supporting Equivalent Circuit Models (ECM 0-RC, 1-RC Thevenin, 2-RC Dual Polarization), Physics-based models (PyBaMM SPM/DFN adapters), and empirical/data-driven models.
- **State Estimation Engine**: State of Charge (SOC), State of Health (SOH), and parameter estimators utilizing Coulomb Counting, Extended Kalman Filters (EKF), and Unscented Kalman Filters (UKF).
- **Electro-Thermal Coupling**: 0D lumped thermal models capturing Joule heating ($I^2 R$) and convective cooling.
- **Multi-Scale Aggregation**: Simulating individual cells, cell-to-cell variances, passive balancing, and full multi-cell packs.

```mermaid
flowchart TD
    subgraph Level 1 Foundation [Level 1: Pure Domain, Canonical Telemetry, Configuration Schemas]
        L1_DOM[src/domain/]
        L1_TEL[src/telemetry/]
        L1_SCH[src/schemas/]
    end

    subgraph Level 2 Modeling & State Estimation Layer
        T21[2.1: Mathematical Core & Model Contracts]
        T22[2.2: Electro-Thermal ECM Models]
        T23[2.3: Physics Model Backend & PyBaMM Adapter]
        T24[2.4: OCV & Chemistry Parameterization Engine]
        T25[2.5: Battery State Estimation Engine]
        T26[2.6: Multi-Cell & Pack Scale Aggregator]
        T27[2.7: Level 2 Validation & Model Gate Review]
    end

    Level 1 Foundation --> T21
    T21 --> T22
    T21 --> T23
    T21 --> T24
    T22 --> T25
    T24 --> T25
    T22 --> T26
    T23 --> T27
    T25 --> T27
    T26 --> T27
```

---

## 1. Architectural Boundaries & Principles

1. **Model Independence & Inversion of Control**: The Digital Twin runtime interacts with battery models strictly through abstract protocols (`BatteryModel`, `StateEstimator`). The platform does not assume ECM or PyBaMM is the sole simulation engine.
2. **Deterministic & Unit-Aware Math**: All physical inputs, state variables, and outputs use explicit SI units (`_v`, `_a`, `_w`, `_c`, `_mohm`, `_f`, `_s`). Floating-point ODE integration is deterministic across environments.
3. **Universality Across Chemistries & Scales**: Mathematical models accept parameters as runtime configuration objects, supporting NMC, LFP (with flat voltage plateau handling), LTO, Sodium-Ion, and Lead-Acid without code modification.
4. **Physical Plausibility & Invariant Defense**: Every model and estimator enforces physical laws:
   - Conservation of charge: $\Delta Q = \int I(t) dt$
   - Conservation of energy: $\Delta E = \int V(t) I(t) dt - Q_{loss}$
   - Bounded state space: $\text{SOC} \in [0.0, 1.0]$, $T > -273.15^\circ\text{C}$, $R_0 \ge 0$.
5. **No Hardware Coupling**: The physical testbench (user's prototype) is strictly one future validation input source. Zero hardware drivers or protocol code will exist in Level 2.

---

## 2. Subtask Breakdown

### Subtask 2.1 — Mathematical Core & Model Contracts
- **Purpose**: Establish abstract state-space interfaces, standardized state/input/output vectors, ODE numerical solvers, and mathematical boundary constraints.
- **Inputs**: Level 1 domain value objects and physical boundary definitions.
- **Outputs**: `BatteryModel` Protocol, `ModelState`, `ModelInput`, `ModelOutput`, `ModelParameters`, numerical integrators (Explicit Euler, RK4).
- **Expected Files**:
  - `src/models/__init__.py`
  - `src/models/base.py`
  - `src/models/types.py`
  - `src/models/math.py`
  - `src/models/exceptions.py`
  - `tests/unit/models/test_math.py`
  - `tests/unit/models/test_base_contracts.py`
- **Dependencies**: Level 1 Domain Foundation.

---

### Subtask 2.2 — Electro-Thermal Equivalent Circuit Models (ECM)
- **Purpose**: Implement high-speed, deterministic 0-RC ($R_{int}$), 1-RC (Thevenin), and 2-RC (Dual Polarization) models coupled with 0D lumped thermal models.
- **Inputs**: `BatteryModel` protocol, `SamplingConfigSchema`, `ECMParametersSchema`.
- **Outputs**: Verified, analytical and discrete ODE step functions for terminal voltage and temperature prediction.
- **Expected Files**:
  - `src/models/ecm/__init__.py`
  - `src/models/ecm/rint.py`
  - `src/models/ecm/thevenin.py`
  - `src/models/ecm/dual_polarization.py`
  - `src/models/thermal/__init__.py`
  - `src/models/thermal/lumped.py`
  - `tests/unit/models/test_ecm_thevenin.py`
  - `tests/unit/models/test_ecm_dual_polarization.py`
  - `tests/unit/models/test_thermal_lumped.py`
- **Dependencies**: Subtask 2.1.

---

### Subtask 2.3 — Physics-Based Model Backend & PyBaMM Adapter
- **Purpose**: Provide an isolated adapter contract for high-fidelity electrochemical solvers (PyBaMM SPM, SPMe, DFN) with graceful fallback for lightweight environments.
- **Inputs**: Abstract physics solver contract, battery profile configuration.
- **Outputs**: `PhysicsModelBackend` ABC, `PyBaMMAdapter` (optional dependency plugin), parameter translation layer.
- **Expected Files**:
  - `src/models/physics/__init__.py`
  - `src/models/physics/base.py`
  - `src/models/physics/pybamm_adapter.py`
  - `tests/unit/models/test_physics_adapter.py`
- **Dependencies**: Subtask 2.1.

---

### Subtask 2.4 — OCV Curves & Chemistry Parameterization Engine
- **Purpose**: Implement non-linear Open-Circuit Voltage vs. State-of-Charge (OCV-SOC) interpolation, temperature-scaling relations (Arrhenius), and default parameter catalogs for all supported chemistries.
- **Inputs**: Tabular and spline OCV data points, chemistry definitions.
- **Outputs**: `OCVCurve` interpolator, temperature scaling utilities, standard reference parameter sets for NMC, LFP, LTO, Sodium-Ion, Lead-Acid.
- **Expected Files**:
  - `src/models/parameters/__init__.py`
  - `src/models/parameters/ocv_curve.py`
  - `src/models/parameters/temperature_scaling.py`
  - `src/models/parameters/chemistry_defaults.py`
  - `tests/unit/models/test_ocv_curve.py`
  - `tests/unit/models/test_temperature_scaling.py`
- **Dependencies**: Subtask 2.1.

---

### Subtask 2.5 — Battery State Estimation Engine (SOC & SOH)
- **Purpose**: Implement real-time estimators for State of Charge (SOC), State of Health (SOH), and internal resistance tracking.
- **Inputs**: Canonical `TelemetrySnapshot`, ECM models, covariance matrices, sensor noise parameters.
- **Outputs**:
  - Coulomb Counter with OCV resting calibration.
  - Extended Kalman Filter (EKF) for non-linear SOC tracking.
  - SOH Capacity & Resistance Degradation Tracker.
- **Expected Files**:
  - `src/estimators/__init__.py`
  - `src/estimators/base.py`
  - `src/estimators/coulomb_counter.py`
  - `src/estimators/ekf.py`
  - `src/estimators/soh.py`
  - `src/estimators/exceptions.py`
  - `tests/unit/estimators/test_coulomb_counter.py`
  - `tests/unit/estimators/test_ekf.py`
  - `tests/unit/estimators/test_soh.py`
- **Dependencies**: Subtasks 2.1, 2.2, 2.4.

---

### Subtask 2.6 — Multi-Cell & Pack Scale Aggregator
- **Purpose**: Aggregate cell-level models into full pack simulations, modeling cell-to-cell variations, current distribution, thermal gradients, and passive cell balancing.
- **Inputs**: `BatteryPack` domain entity, cell-level `BatteryModel` instances.
- **Outputs**: `PackModel` simulation wrapper predicting pack terminal voltage, cell voltage dispersion, and hotspot temperatures.
- **Expected Files**:
  - `src/models/aggregator/__init__.py`
  - `src/models/aggregator/pack_model.py`
  - `src/models/aggregator/balancing_model.py`
  - `tests/unit/models/test_pack_model.py`
  - `tests/unit/models/test_balancing_model.py`
- **Dependencies**: Subtasks 2.1, 2.2.

---

### Subtask 2.7 — Level 2 Model Verification & Gate Review
- **Purpose**: Comprehensive gate review auditing mathematical credibility, conservation laws, numerical stability under dynamic drive cycles (WLTP/Pulse), and estimator convergence.
- **Inputs**: All Level 2 models, estimators, parameter catalogs, and test suites.
- **Outputs**: Formal Level 2 Gate Report (`docs/models-validation.md`) and sign-off.
- **Dependencies**: Subtasks 2.1 through 2.6.

---

## 3. Implementation Sequence

```text
┌────────────────────────────────────────────────────────────────────────┐
│ Subtask 2.1: Mathematical Core & Model Contracts (Foundational Step)   │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
         ┌──────────────────────────┴──────────────────────────┐
         ▼                                                     ▼
┌─────────────────────────────────────┐       ┌─────────────────────────────────────┐
│ Subtask 2.2: Electro-Thermal ECM    │       │ Subtask 2.4: OCV & Chemistry Engine │
└──────────────────┬──────────────────┘       └──────────────────┬──────────────────┘
                   │                                             │
                   ├──────────────────────────┬──────────────────┘
                   ▼                          ▼
┌─────────────────────────────────────┐ ┌───────────────────────────────────────────┐
│ Subtask 2.6: Pack Model Aggregator  │ │ Subtask 2.5: State Estimation Engine      │
└──────────────────┬──────────────────┘ └──────────────────┬────────────────────────┘
                   │                                       │
                   └──────────────────┬────────────────────┘
                                      ▼
┌────────────────────────────────────────────────────────────────────────┐
│ Subtask 2.3: Physics Model Backend & PyBaMM Adapter                    │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ Subtask 2.7: Level 2 Validation & Model Gate Review                    │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Explicitly Deferred Subsystems (Non-Level 2 Scope)

The following components are strictly out of scope for Level 2 and will be addressed in future milestones:
- **Telemetry Ingestion & Protocols** (MQTT, WebSockets, CAN bus) $\rightarrow$ **Level 3 (Runtime & Ingestion)**.
- **Hardware Drivers & BMS Serial Adapters** (ESP32, STM32, Serial) $\rightarrow$ **Level 3**.
- **Persistence & Time-Series Storage** (TimescaleDB / PostgreSQL) $\rightarrow$ **Level 3 / 4**.
- **REST & GraphQL Application APIs** (FastAPI) $\rightarrow$ **Level 4**.
- **Frontend User Interface & Web Dashboard** (React / Vite) $\rightarrow$ **Level 5**.
- **Machine Learning Surrogate Retraining Pipelines** $\rightarrow$ **Level 6**.
