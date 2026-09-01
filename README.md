# TwinVolt — Universal Battery Digital Twin Platform

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Development Status](https://img.shields.io/badge/Status-Under%20Active%20Bootstrap-orange.svg)](#current-development-status)

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

1. **Battery Agnostic**: Supports any cell chemistry (e.g., NMC, LFP, LCO, NCA, LTO, Solid-State, Sodium-ion), form factor (cylindrical, pouch, prismatic), and pack configuration (series/parallel topologies) via parametric configuration.
2. **Model Agnostic**: Decouples the Digital Twin engine from specific mathematical representations. Supports Equivalent Circuit Models (Thevenin, 2-RC), electrochemical physics models (e.g., PyBaMM/DFN/SPM), and neural/empirical models behind a unified interface.
3. **Hardware Agnostic**: Independent of any specific BMS microcontroller, analog front-end (AFE), or hardware vendor.
4. **Protocol Agnostic**: Ingests telemetry across diverse industrial and embedded communication protocols (MQTT, CAN bus, Modbus, BLE, Serial/UART, WebSocket, REST) using pluggable adapters.
5. **Modular Architecture**: Built with clear boundary layers and dependency inversion, allowing individual components (e.g., estimation algorithms, adapters, storage backends) to be swapped without system redesign.
6. **Separation of Concerns**: Strict isolation between physical data ingestion, canonical data structures, domain modeling, state estimation, data persistence, and visualization.
7. **Dual Battery Support (Physical + Virtual)**: Operates seamlessly with live hardware telemetry, historical replay datasets, or purely synthetic/simulated load profiles.
8. **High Testability**: Every layer is architected for rigorous automated testing—from unit-level mathematical checks to simulated synthetic stress tests and hardware-in-the-loop (HIL) harnesses.
9. **Extensibility**: Standardized plugin points for custom state estimators (Kalman filters, particle filters, ML estimators), new communication adapters, and analytics modules.
10. **Future Scalability**: Designed to scale from single-cell laboratory testbenches to distributed multi-pack fleet monitoring architectures.

---

## 4. Current Development Status

> [!IMPORTANT]
> **TwinVolt is currently in early-stage active development (Milestone 0: Repository & Foundation Bootstrap).**

The repository currently establishes the foundational project structure, guidelines, and architecture definitions. **No application layers, physics engines, estimators, or web services have been implemented yet.** Implementation will proceed systematically across structured milestones.

| Layer / Feature Area | Status | Planned Phase |
| :--- | :--- | :--- |
| **Repository Structure & Docs** | **Established** | Milestone 0 |
| **Domain Entities & Canonical Schema** | *Planned* | Milestone 1 |
| **Battery Model Abstraction & Engines** | *Planned* | Milestone 2 |
| **Data Acquisition & Protocol Adapters** | *Planned* | Milestone 3 |
| **Digital Twin Core Engine** | *Planned* | Milestone 4 |
| **State Estimation (SOC / SOH / SOP)** | *Planned* | Milestone 5 |
| **Backend Data Platform & APIs** | *Planned* | Milestone 6 |
| **Frontend Dashboard & 3D Visualization** | *Planned* | Milestone 7 |

---

## 5. High-Level Architecture

TwinVolt follows a clean unidirectional data flow and modular layered architecture:

```text
┌─────────────────────────────────────────────────────────────────────────┐
│                    Physical / Virtual Data Sources                      │
│   (BMS Hardware, CAN Loggers, Laboratory Cyclers, Synthetic Profiles)  │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    Data Acquisition / Adapter Layer                     │
│    (MQTT Ingestion, CAN Bus, Serial/UART, Modbus, Replay Handlers)      │
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
│                      Universal Battery Domain                           │
│        (Pack Topologies, Chemistry Profiles, Thermal Boundaries)        │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      Battery Model Abstraction                          │
│         (Equivalent Circuit Models, Electrochemical / PyBaMM, ML)        │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         Digital Twin Core                               │
│       (State Synchronization, Parameter Tracking, Twin Co-Simulation)   │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│           State Estimation / Analytics / Fault Detection / Prediction    │
│       (EKF/UKF SOC, SOH Capacity Fade, Thermal Runaway Alerts, RUL)     │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     Backend / Data Platform                             │
│     (FastAPI Services, TimescaleDB/PostgreSQL, Redis Streams/Cache)     │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     Frontend / Visualization                            │
│     (Real-Time Web Dashboard, Cell Matrix Heatmaps, Twin Metrics UI)    │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 6. Planned Capabilities

- **Real-Time Telemetry Normalization**: Ingestion of voltage, current, internal resistance, and multi-point temperature data into a strictly typed canonical format.
- **Dynamic State Estimation**:
  - *SOC (State of Charge)*: Coulomb counting with Extended Kalman Filter (EKF) and Unscented Kalman Filter (UKF) drift correction.
  - *SOH (State of Health)*: Capacity fade tracking and internal impedance growth tracking.
  - *SOP (State of Power)*: Dynamic continuous and peak charge/discharge power limits.
- **High-Fidelity Simulation & Physics Integration**: Co-simulation using Equivalent Circuit Models (ECM 1-RC, 2-RC) and electrochemical models (e.g., PyBaMM).
- **Fault Detection & Safety Monitoring**: Real-time detection of over-voltage, under-voltage, thermal runaway precursors, cell imbalance, sensor anomalies, and internal short-circuit indicators.
- **Predictive Analytics & RUL**: Degradation modeling and Remaining Useful Life forecasting under varying cycling and temperature profiles.
- **Hardware-in-the-Loop & Virtual Testbench**: Ability to run full digital twin validation with or without physical hardware present.

---

## 7. Planned Technology Areas

- **Core & Analytics Engine**: Python 3.11+, NumPy, SciPy, Pandas, PyBaMM (Electrochemical modeling)
- **State Estimation & Filtering**: FilterPy, custom Kalman Filter implementations
- **Backend & Ingestion Services**: FastAPI, Pydantic (data validation), Uvicorn, asyncio
- **Message Broker & Telemetry**: Eclipse Mosquitto (MQTT), python-can, PySerial
- **Data Storage**: TimescaleDB / PostgreSQL (time-series & metadata), Redis (real-time cache & message streaming)
- **Frontend & Visualization**: Modern TypeScript / React, Vite, Tailwind CSS, Recharts / ECharts, Three.js (for pack 3D cell visualization)
- **Infrastructure & Tooling**: Docker, Docker Compose, pytest, Ruff, mypy

---

## 8. Development Methodology

TwinVolt follows a disciplined, test-driven, and milestone-oriented software engineering lifecycle:

1. **Architecture-First**: Every module is defined by explicit interfaces and contracts before implementation.
2. **Strict Incremental Stages**: Work progresses through documented, verifiable subtasks (Milestone 0 through Milestone N).
3. **Type Safety & Validation**: Comprehensive type hints (Python `typing`, Pydantic, TypeScript) and linting across all codebases.
4. **Contract-Driven Communication**: Canonical data schemas act as single sources of truth across ingestion, core modeling, and frontend visualization.
5. **Continuous Verification**: Unit tests, integration tests, and synthetic data regression tests accompany all functional changes.
6. **Rigorous Git & Workflow Governance**: Adherence to Conventional Commits, branch protection, PR checklists, and release lifecycles — see [docs/git-workflow.md](docs/git-workflow.md).

---

## 9. Repository Structure

```text
TwinVolt-Digital-Twin/
│
├── README.md               # Root platform documentation & architectural overview
├── LICENSE                 # MIT open-source license
├── .gitignore              # Multi-stack Git ignore rules
├── .env.example            # Template configuration & environment variables
│
├── docs/                   # System specifications, architecture decisions & guides
│   └── README.md
│
├── src/                    # Production source code (Core, Adapters, Estimation, API)
│   └── README.md
│
├── tests/                  # Test suites (Unit, Integration, Simulation, HIL)
│   └── README.md
│
└── scripts/                # Development, setup, profiling & maintenance scripts
    └── README.md
```

---

## 10. Testing Philosophy

TwinVolt considers robust automated testing foundational for safety-critical battery engineering:

- **Unit Testing**: Isolated verification of mathematical algorithms, filtering routines, OCV-SOC lookup tables, and canonical data validators.
- **Synthetic Simulation Testing**: Running the Digital Twin against standardized synthetic drive cycles (e.g., WLTP, US06) and constant-current constant-voltage (CCCV) load profiles to verify mathematical stability.
- **Integration Testing**: End-to-end verification of telemetry ingestion, message queues, time-series persistence, and API endpoints.
- **Fault Injection Testing**: Simulating packet drops, sensor noise, voltage spikes, and sudden temperature jumps to validate anomaly detection resilience.
- **Hardware-in-the-Loop (HIL) Testing**: Testing against bench hardware via hardware-agnostic communication adapters.

---

## 11. Hardware Integration Philosophy

TwinVolt is fundamentally **hardware-independent**. 

- Physical hardware (e.g., custom BMS prototypes, commercial battery packs, laboratory cyclers) interacts with TwinVolt solely via **Data Acquisition Adapters**.
- Any specific hardware prototype—such as a small 2S/3S Li-ion prototype testbench—is treated strictly as **one external telemetry provider and validation source**.
- No hardware-specific constraints, hardcoded cell counts, pinouts, or bespoke protocols will ever be embedded within the core Digital Twin domain models or state estimation algorithms.

---

## 12. License

This project is licensed under the **MIT License** — see the [LICENSE](LICENSE) file for details.
