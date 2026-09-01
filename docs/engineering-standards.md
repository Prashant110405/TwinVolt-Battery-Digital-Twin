# TwinVolt — Engineering Standards & Development Conventions

[![Status: Active Standard](https://img.shields.io/badge/Standard-Active-green.svg)](#)
[![Compliance: Mandatory](https://img.shields.io/badge/Compliance-Mandatory-red.svg)](#)

---

## Document Overview & Purpose

This document defines the formal **engineering standards, coding conventions, architectural boundaries, and quality benchmarks** for the **TwinVolt Universal Battery Digital Twin Platform**.

TwinVolt is a serious, long-term engineering software project designed to model, simulate, and predict the behavior of diverse battery systems. To maintain architectural purity, prevent technical debt, and ensure scalability across teams and milestones, all contributions—whether from student developers, researchers, or industry contributors—**must strictly adhere to the standards set forth in this document**.

---

## Table of Contents

1. [Section 1 — Technology Baseline & Version Policy](#section-1--technology-baseline--version-policy)
2. [Section 2 — Python Coding Standards](#section-2--python-coding-standards)
3. [Section 3 — Code Quality & Static Analysis](#section-3--code-quality--static-analysis)
4. [Section 4 — Type Safety & Data Modeling](#section-4--type-safety--data-modeling)
5. [Section 5 — Documentation Standards](#section-5--documentation-standards)
6. [Section 6 — Error Handling & Exception Strategy](#section-6--error-handling--exception-strategy)
7. [Section 7 — Logging & Observability Standards](#section-7--logging--observability-standards)
8. [Section 8 — Configuration Management](#section-8--configuration-management)
9. [Section 9 — Dependency Management](#section-9--dependency-management)
10. [Section 10 — Architectural Dependency Rules](#section-10--architectural-dependency-rules)
11. [Section 11 — Battery-Agnostic Development Rule](#section-11--battery-agnostic-development-rule)
12. [Section 12 — Model-Agnostic Development Rule](#section-12--model-agnostic-development-rule)
13. [Section 13 — Hardware & Protocol Agnostic Rule](#section-13--hardware--protocol-agnostic-rule)
14. [Section 14 — Testing Philosophy & Strategy](#section-14--testing-philosophy--strategy)
15. [Section 15 — Security Standards](#section-15--security-standards)
16. [Section 16 — Version Control & Git Standards](#section-16--version-control--git-standards)
17. [Section 17 — Code Review Standard](#section-17--code-review-standard)
18. [Section 18 — Definition of Done (DoD)](#section-18--definition-of-done-dod)
19. [Section 19 — Core Engineering Principles Summary](#section-19--core-engineering-principles-summary)

---

## Section 1 — Technology Baseline & Version Policy

TwinVolt establishes a modern, stable, and reproducible technology baseline. Tools and versions are selected based on industrial longevity, type safety, and ecosystem maturity.

```text
┌─────────────────────────────────────────────────────────────────────────┐
│                        TwinVolt Technology Stack                        │
├────────────────────────┬────────────────────────────────────────────────┤
│ Runtime / Language     │ Python 3.11+ (Backend & Analytics)             │
│ Frontend Runtime       │ Node.js 20+ LTS (TypeScript 5.x+ / React 18+)  │
│ Primary Linter/Format  │ Ruff (Python), ESLint + Prettier (TypeScript)  │
│ Type Checking          │ mypy (strict mode), TypeScript compiler        │
│ Relational Database    │ PostgreSQL 16+ with TimescaleDB extension      │
│ In-Memory / Streaming  │ Redis 7+                                       │
│ Telemetry Transport    │ MQTT v3.1.1 / v5.0 (Eclipse Mosquitto)         │
│ API Framework          │ FastAPI + Pydantic v2 + Uvicorn                │
│ Battery Physics Engine │ PyBaMM (Pluggable backend among other models)   │
│ Containerization       │ Docker & Docker Compose v2+                    │
│ Test Framework         │ pytest (Python), Vitest / Jest (Frontend)      │
└────────────────────────┴────────────────────────────────────────────────┘
```

### 1.1 Python Version Policy
- **Minimum Supported Version**: Python `3.11`.
- **Rationale**: Python 3.11+ delivers substantial CPython runtime performance improvements (~25% speedups), enhanced tracebacks, and modern typing primitives (`Self`, `TypeVarTuple`, `dataclass_transform`, Exception Groups).
- **Forward Compatibility**: Features deprecated in upcoming Python versions must not be introduced.

### 1.2 Python Package & Environment Management
- All Python dependencies must be managed via standard `pyproject.toml` configurations.
- Virtual environments (`.venv`) are mandatory for local development to ensure isolated, reproducible dependency trees.
- Pinned dependency locks will be used for production builds and deterministic CI runs.

### 1.3 TypeScript & Node.js Version Policy (Frontend)
- **Node.js**: Active Long-Term Support (LTS) release (Node.js 20+).
- **TypeScript**: TypeScript 5.x+ with strict mode (`"strict": true`) strictly enforced.
- **Frontend Framework**: React 18+ utilizing functional components, hooks, Vite for bundling, and Tailwind CSS for modular styling.

### 1.4 Infrastructure & Containerization
- **Docker & Docker Compose**: All external services (PostgreSQL/TimescaleDB, Redis, Mosquitto MQTT broker) must have standardized Docker Compose definitions for one-command local developer bootstrapping.
- Production images must use multi-stage, non-root, minimal base images (e.g., `python:3.11-slim` or distroless).

### 1.5 Pluggable Model Engines
- **PyBaMM**: Treated as **one supported battery-model engine**, not the exclusive modeling foundation. Equivalent Circuit Models (ECM), empirical models, and machine-learning estimators share equal architectural standing.

---

## Section 2 — Python Coding Standards

All Python source code must adhere strictly to modern Python idioms and style guidelines.

### 2.1 PEP 8 Compliance & Code Style
- Code must comply with **PEP 8** style guidelines.
- Standard line length limit is **88 characters** (matching Black/Ruff standards), with an absolute maximum of **100 characters** for long mathematical expressions or docstrings.
- Indentation: Exactly **4 spaces** per indentation level (no tabs).

### 2.2 Naming Conventions
- **Classes / Types / Protocols / Enums**: `PascalCase` (e.g., `BatteryStateEstimator`, `CellTelemetry`, `EquivalentCircuitModel`).
- **Functions / Methods / Variables / Attributes**: `snake_case` (e.g., `estimate_soc()`, `pack_voltage`, `cell_temperatures`).
- **Constants**: `UPPER_SNAKE_CASE` (e.g., `FARADAY_CONSTANT`, `DEFAULT_SIMULATION_STEP_MS`).
- **Modules & Packages**: Short, lowercase `snake_case` with no hyphens (e.g., `canonical_telemetry.py`, `state_estimation/`).
- **Private / Internal Members**: Single leading underscore `_private_method()`. Avoid name-mangled double underscores `__name` unless strictly preventing inheritance clashes.

### 2.3 Function & Method Design
- **Single Responsibility Principle (SRP)**: Each function must perform exactly one well-defined operation.
- **Small Footprint**: Functions should ideally not exceed 40-50 lines of logic. Complex algorithms must be broken down into composable, pure helper functions.
- **Purity Where Possible**: Prefer pure functions (output depends solely on inputs with zero side-effects) for mathematical routines, filtering steps, and data transformations.
- **Explicit Arguments**: Avoid catch-all `*args` and `**kwargs` in domain and core APIs unless implementing decorators or pass-through proxies.

### 2.4 Class Design & OOP Principles
- **Favor Composition Over Inheritance**: Use composition to combine behaviors instead of creating deep, brittle class hierarchies.
- **Dataclasses & Pydantic Models**: Use `@dataclass(frozen=True)` for immutable internal data containers and `pydantic.BaseModel` for validation at system boundaries (APIs, schemas, configs).
- **Explicit Interfaces**: Abstract interfaces must use `typing.Protocol` (structural subtyping) or `abc.ABC` with `@abstractmethod` (nominal subtyping).

### 2.5 State & Dependency Management
- **No Global State**: Mutable module-level globals are strictly prohibited. Global variables lead to concurrency race conditions and make deterministic testing impossible.
- **Dependency Injection**: Pass dependencies (such as loggers, clocks, adapters, and model providers) explicitly via constructors or factory methods rather than instantiating them internally.
- **No Circular Dependencies**: Circular imports indicate flawed domain boundaries. Code must be structured hierarchically: low-level domain -> high-level orchestration.

---

## Section 3 — Code Quality & Static Analysis

TwinVolt maintains high code quality through continuous automated linting, formatting, and static analysis.

```text
Developer Edit ──► Ruff Linter & Formatter ──► mypy (Strict) ──► pytest Suite ──► Clean PR
```

### 3.1 Tooling: Ruff & Mypy
- **Primary Linter & Formatter**: [Ruff](https://docs.astral.sh/ruff/) is the official Python linter and code formatter across the entire repository.
- **Type Checker**: [mypy](https://mypy.readthedocs.io/) in strict mode (`--strict`).

### 3.2 Import Organization
Imports must be sorted and grouped automatically by Ruff according to standard isort rules:
1. Standard library imports (e.g., `import math`, `from typing import Protocol`).
2. Related third-party imports (e.g., `import numpy as np`, `from pydantic import BaseModel`).
3. Local application / domain imports (e.g., `from src.domain.entities import Cell`).
4. Wildcard imports (`from module import *`) are **strictly prohibited**.

### 3.3 Zero-Tolerance Policy for Errors
- All code committed to the repository must pass `ruff check`, `ruff format --check`, and `mypy` with **zero errors**.
- Compiler and linter warnings must be resolved, not ignored. Lint suppressions (`# noqa`, `# type: ignore`) require an accompanying inline comment explaining the technical necessity.

### 3.4 Cleanliness & Dead Code
- **No Dead Code**: Unused imports, unreachable statements, and orphaned functions must be removed immediately.
- **No Commented-Out Code**: Abandoned code blocks must not be committed. Git history preserves past implementations.
- **Avoid Premature Abstraction**: Do not create abstract factories or complex design patterns for operations that only have a single concrete implementation.

---

## Section 4 — Type Safety & Data Modeling

Battery Digital Twins process high-velocity physical measurements, electro-thermal parameters, and safety-critical state estimates. Type safety is non-negotiable.

### 4.1 Modern Type Annotations
All function signatures (arguments and return types) and class attributes must have explicit type annotations:

```python
# GOOD: Explicit, modern typing with clear semantics
def calculate_terminal_voltage(
    open_circuit_voltage: float,
    current_amperes: float,
    internal_resistance_ohms: float,
    rc_polarization_voltages: list[float],
) -> float:
    ...

# BAD: Untyped or ambiguous signature
def calc_volt(ocv, i, r, rc):
    ...
```

### 4.2 Prohibited & Discouraged Patterns
- **No Blanket `Any`**: The use of `typing.Any` is prohibited in core domain logic, telemetry processing, and state estimation algorithms.
- **No Untyped Dictionaries**: Inter-module data passing must not use unstructured `dict[str, Any]`. Use typed Pydantic models, NamedTuples, or dataclasses.
- **No Stringly-Typed States**: System states, operational modes, and battery chemistries must use `enum.Enum` or `typing.Literal`, never arbitrary strings.

```python
# GOOD: Enumerated chemistry types
class BatteryChemistry(str, Enum):
    NMC = "NMC"
    LFP = "LFP"
    LCO = "LCO"
    NCA = "NCA"
    LTO = "LTO"

# BAD: Loose string comparison
if chemistry == "nmc_battery":  # Prone to typos and casing bugs
    ...
```

---

## Section 5 — Documentation Standards

Code must be self-documenting in structure and explicitly documented in purpose.

### 5.1 Docstring Conventions
- All public modules, classes, methods, and functions must include docstrings formatted according to the **Google Python Style Guide**.
- Docstrings must specify:
  - Concise summary of purpose.
  - **Args**: Argument names, types, and physical units (e.g., Volts, Amperes, Kelvin, Seconds).
  - **Returns**: Return value description, type, and physical units.
  - **Raises**: Explicit exceptions that may be raised under failure conditions.

### 5.2 Explaining "WHY", Not "WHAT"
- Documentation should explain **why** an engineering or mathematical decision was made, not merely repeat what the code obviously does.
- Good: `"""Applies a 2-stage Savitzky-Golay filter to smooth dV/dQ derivatives without introducing phase lag in phase transition zones."""`
- Bad: `"""Filters the voltage data."""`

### 5.3 Mathematical & Physics Documentation
- Complex mathematical equations (e.g., Kalman filter Riccati equations, Butler-Volmer kinetics, equivalent RC circuit differential equations) must include:
  - LaTeX mathematical notation in the docstring or accompanying documentation.
  - Literature citations or academic paper references where the formulation originates.
  - Clear definitions of all variables and their physical SI units.

### 5.4 Architecture Decision Records (ADRs)
- Significant architectural decisions (e.g., adopting a specific state estimator, choosing time-series storage engines, defining canonical schema formats) must be recorded as an ADR in `docs/adr/`.

---

## Section 6 — Error Handling & Exception Strategy

TwinVolt must maintain reliable, deterministic execution even when ingesting noisy telemetry or encountering physical sensor dropouts.

```text
┌─────────────────────────────────────────────────────────────┐
│                       TwinVoltError                         │
│                    (Base Custom Exception)                  │
├──────────────────────────────┬──────────────────────────────┤
│ ConfigurationError           │ TelemetryValidationError     │
│ ModelConvergenceError        │ StateEstimationError         │
│ ProtocolAdapterError         │ ThermalLimitExceededError    │
└──────────────────────────────┴──────────────────────────────┘
```

### 6.1 Custom Domain Exception Hierarchy
- All application-specific exceptions must inherit from a common base class: `TwinVoltError`.
- Specific sub-exceptions must be created for distinct failure domains (e.g., `InvalidBatteryConfigurationError`, `TelemetryDecodingError`, `ModelDivergenceError`).

### 6.2 Strict Failure Handling Rules
1. **No Silent Failures**: Never suppress exceptions silently. Bare `except:` or `except Exception: pass` is **strictly forbidden**.
2. **Fail-Fast on Invalid Configurations**: If a battery configuration contains unphysical parameters (e.g., negative capacity, zero cell count), the system must reject it immediately at startup.
3. **Fail-Safe in Telemetry Streams**: If an individual telemetry packet is corrupted, the ingestion adapter must log a warning, increment an anomaly counter, and discard the single invalid packet without crashing the long-running twin engine.
4. **Separation of Internal vs. External Errors**: Internal exception stack traces must never be leaked directly to external API clients; APIs must return sanitized, structured error responses.

---

## Section 7 — Logging & Observability Standards

Logging provides visibility into the state, health, and convergence of the Digital Twin.

### 7.1 Structured Logging
- Logs must use structured formats (JSON in production, formatted key-value in development).
- Always attach contextual metadata attributes (e.g., `twin_id="twin-01"`, `pack_id="pack-03"`, `cell_index=2`).

### 7.2 Log Level Guidelines

| Level | Intended Usage | Example |
| :--- | :--- | :--- |
| **`DEBUG`** | Detailed diagnostic information for developers during troubleshooting. | `EKF state covariance matrix updated: trace=0.0024` |
| **`INFO`** | Normal operational milestones and lifecycle events. | `Twin initialized for battery 'NMC-3S1P-Pack-A'` |
| **`WARNING`** | Unexpected situations or minor anomalies handled gracefully. | `Telemetry packet jitter exceeded 200ms threshold` |
| **`ERROR`** | Significant operational failures affecting a specific task or request. | `Failed to parse CAN frame ID 0x18FF50E5` |
| **`CRITICAL`** | Severe failures causing service shutdown or severe safety alerts. | `Thermal runaway precursor detected: dT/dt > 1.5 K/s` |

### 7.3 Prohibited Logging Practices
- **Never Log Secrets**: Passwords, API tokens, MQTT private credentials, and connection strings must never appear in logs.
- **No High-Frequency Loop Spam**: Do not log individual messages inside high-frequency real-time loops (e.g., 100 Hz sensor feeds). Use rolling metrics, downsampled logging, or event-driven alert triggers.

---

## Section 8 — Configuration Management

Configuration must be completely decoupled from application logic following 12-Factor App methodology.

### 8.1 Core Configuration Rules
1. **Zero Hardcoded Secrets / Settings**: No URLs, ports, credentials, or environment flags may be hardcoded into business logic.
2. **Never Commit Secrets**: Real `.env` files, SSH keys, certificates, and passwords must never be tracked in Git.
3. **Validated Environment Variables**: All runtime settings must be parsed and validated through strongly-typed settings classes (e.g., Pydantic `BaseSettings`).
4. **Separation of Battery Profiles**: Battery chemistry profiles, pack definitions, and cell parameters are **domain configuration datasets**, not software settings. They must be stored in declarative formats (YAML/JSON) independent of the core codebase.
5. **Documented Defaults**: Every configuration key must have a safe, documented default in [.env.example](file:///.env.example).

---

## Section 9 — Dependency Management

Dependencies introduce maintenance overhead, security vulnerability surface, and potential licensing conflicts.

### 9.1 Dependency Evaluation Criteria
Before introducing any new third-party dependency, verify:
1. **Necessity**: Is the library truly necessary, or can the functionality be cleanly implemented with the standard library in < 50 lines?
2. **Maintenance & Maturity**: Is the project actively maintained with a strong community, regular releases, and clean issue tracker?
3. **License Compatibility**: Is the library licensed under an MIT, Apache 2.0, BSD, or compatible permissive open-source license?
4. **Footprint**: Does the package bring in dozens of transitive dependencies?

### 9.2 Dependency Hygiene
- Separate **runtime dependencies** (e.g., `fastapi`, `numpy`, `scipy`, `pydantic`) from **development/testing dependencies** (e.g., `pytest`, `ruff`, `mypy`).
- Regularly audit dependencies for security vulnerabilities and remove unused packages.

---

## Section 10 — Architectural Dependency Rules

TwinVolt enforces strict architectural layer boundaries and **Inversion of Control (Dependency Inversion Principle)**.

```text
┌─────────────────────────────────────────────────────────────────────────┐
│                           Frontend / UI Layer                           │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │ (REST / WebSocket)
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     Infrastructure & Backend Services                   │
│          (FastAPI, PostgreSQL/TimescaleDB, Redis, MQTT Broker)          │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    Data Acquisition / Adapters Layer                    │
│           (MQTT Client, CAN Driver, Serial Port, File Replay)           │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │ (Implements Contracts)
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│               Digital Twin Core & State Estimation Engine               │
│               (Twin Synchronization, EKF/UKF, Degradation)              │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │ (Interacts via Abstractions)
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    Battery Model Abstraction Layer                      │
│                  (Abstract Models: ECM, PyBaMM, ML)                     │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │ (Depends on Pure Domain)
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      Universal Battery Domain                           │
│     (Pure Business Logic: Pack Topologies, Cell States, Schemas)        │
└─────────────────────────────────────────────────────────────────────────┘
```

### 10.1 The Golden Boundary Rule
- **Higher-level infrastructure components may depend on lower-level domain abstractions, but the Domain must NEVER depend on Infrastructure.**
- The **Universal Battery Domain** must be pure Python. It must **NEVER** import or depend upon:
  - `fastapi` or HTTP frameworks.
  - `asyncpg`, `sqlalchemy`, or specific database drivers.
  - `paho-mqtt` or networking libraries.
  - `pySerial`, `python-can`, or hardware drivers.
  - `pybamm` or specific third-party simulation engines.
- Domain logic interacts with the outside world exclusively through **abstract interfaces and protocols**.

---

## Section 11 — Battery-Agnostic Development Rule

> [!CRITICAL]
> **TwinVolt is a UNIVERSAL platform. No core component may ever hardcode assumptions about a specific battery pack, chemistry, or cell count.**

```text
       WRONG (Hardcoded)                          CORRECT (Universal & Parametric)
┌──────────────────────────────┐           ┌──────────────────────────────────────────────┐
│ def get_cell_3_voltage():    │           │ def get_cell_voltage(cell_index: int):       │
│     return v3                │           │     return self.cells[cell_index].voltage    │
│                              │    VS     │                                              │
│ if chemistry == "LFP":       │           │ ocv = battery_profile.ocv_curve.lookup(soc)  │
│     max_v = 3.65             │           │                                              │
└──────────────────────────────┘           └──────────────────────────────────────────────┘
```

### 11.1 Prohibited Assumptions in Core Code
No core TwinVolt component may assume:
- A fixed cell count (e.g., 2S, 3S, 4S, 16S, 96S, etc.).
- A specific series/parallel topology (e.g., 3S1P).
- A specific battery chemistry (e.g., Lithium-ion, LFP, NMC, LCO, Solid-State).
- A fixed nominal, minimum, or maximum voltage (e.g., 3.7V, 4.2V, 12.6V, 400V, 800V).
- A fixed nominal capacity (e.g., 2.2 Ah, 50 Ah, 100 Ah).
- A specific BMS vendor, microcontroller (e.g., ESP32, STM32, Arduino), or sensor model.

### 11.2 Parametric Representation
- All battery characteristics must be supplied through **explicit domain entities and configuration profiles**.
- Dynamic cell arrays must use generic collections (e.g., `list[CellState]`, `pack.series_count`) rather than hardcoded index access.

---

## Section 12 — Model-Agnostic Development Rule

TwinVolt must remain independent of any single battery modeling library or mathematical approach.

### 12.1 Pluggable Model Abstractions
- The Digital Twin Core interacts with models via a generic `BatteryModel` abstract interface.
- Supported modeling paradigms include:
  1. **Equivalent Circuit Models (ECM)**: 1-RC (Thevenin), 2-RC, 3-RC models for fast real-time estimation.
  2. **Electrochemical Physics Models**: Single Particle Model (SPM), Doyle-Fuller-Newman (DFN) via PyBaMM.
  3. **Empirical & Look-Up Table Models**: OCV-SOC static maps, empirical Peukert capacity models.
  4. **Data-Driven / Neural Models**: Machine learning state-of-charge and degradation models.
- **PyBaMM is one pluggable backend**, not the foundational core of TwinVolt. The platform must execute seamlessly even in lightweight environments where PyBaMM is not installed.

---

## Section 13 — Hardware & Protocol Agnostic Rule

Physical battery hardware interacts with TwinVolt through decoupled adapter boundaries.

### 13.1 Canonical Telemetry Contract
- All data ingestion adapters (MQTT, CAN, Serial/UART, BLE, Modbus, HTTP REST, File Replay) must decode raw incoming packets into a single, unified **Canonical Telemetry Data Structure**.
- The core Digital Twin engine only consumes canonical telemetry objects; it has zero knowledge of how the data was physically transported.

### 13.2 Role of Hardware Prototypes
- Any physical hardware—including the user's 2S/3S Li-ion prototype—serves strictly as **one external validation data source**.
- Hardware prototypes must never dictate data structures, communication rates, or internal representations.

---

## Section 14 — Testing Philosophy & Strategy

Reliability in battery state estimation requires continuous, multi-tiered verification.

```text
           ┌────────────────────────────────────────┐
           │        Hardware-in-the-Loop (HIL)      │  ◄── Physical Testbenches
           ├────────────────────────────────────────┤
           │      System / End-to-End Tests         │  ◄── Full Data Pipelines
           ├────────────────────────────────────────┤
           │   Simulation & Synthetic Benchmarks    │  ◄── WLTP, US06, CCCV Cycles
           ├────────────────────────────────────────┤
           │           Integration Tests            │  ◄── Adapter -> Core -> DB
           ├────────────────────────────────────────┤
           │              Unit Tests                │  ◄── Fast, Pure Math & Logic
           └────────────────────────────────────────┘
```

### 14.1 Test Hierarchy
1. **Unit Tests**: Test pure algorithms, mathematical formulas, and validators in total isolation. Fast execution (< 50ms per test).
2. **Integration Tests**: Verify inter-module data pipelines (e.g., telemetry parser -> canonical builder -> state estimator).
3. **Simulation Benchmark Tests**: Run the Digital Twin against standard drive cycles (WLTP, US06, UDDS, synthetic pulse discharges) to verify estimator convergence and tracking accuracy against mathematical ground truth.
4. **System Tests**: End-to-end verification of REST endpoints, WebSocket streams, and background worker queues.
5. **Hardware-in-the-Loop (HIL) Tests**: Verify real serial/CAN communication with physical or emulated BMS hardware. HIL tests must be segregated from fast CI pipelines.

### 14.2 Testing Best Practices
- **Deterministic Runs**: State estimation tests using Kalman filters or synthetic noise must use explicit, fixed random seeds (`np.random.seed(42)`).
- **Regression Testing**: Every bug fix must include a test reproducing the original issue to prevent regressions.
- **Mocking External I/O**: Unit tests must never initiate real network connections, write to production databases, or require physical hardware.

---

## Section 15 — Security Standards

Security must be designed into all data pipelines and service boundaries from the start.

### 15.1 Baseline Security Rules
1. **Zero Hardcoded Credentials**: Strictly ban passwords, API tokens, or secret keys in source code.
2. **Untrusted Telemetry Principle**: Treat all incoming telemetry (MQTT, CAN, Serial, HTTP) as untrusted input. Validate data ranges, types, and frame lengths before processing.
3. **No Unsafe Execution**: Strictly prohibit dynamic code execution (`eval()`, `exec()`, `pickle.loads()` on untrusted streams).
4. **Least Privilege**: Application containers, database users, and broker clients must run with minimum required operational permissions.
5. **Sanitized Error Responses**: Never return database connection strings, file paths, or internal tracebacks in public API error payloads.

---

## Section 16 — Version Control & Git Standards

A clean, traceable Git history is essential for collaborative engineering.

### 16.1 Conventional Commits Specification
All commit messages must follow the [Conventional Commits](https://www.conventionalcommits.org/) standard:

```text
<type>(<optional scope>): <short imperative description>

[optional detailed body explaining WHY the change was made]

[optional footer(s) like issue references: Fixes #123]
```

#### Allowed Commit Types:
- `feat`: A new user-facing or platform capability.
- `fix`: A bug fix or error correction.
- `docs`: Documentation additions or updates only.
- `test`: Adding or modifying automated test suites.
- `refactor`: Code restructuring without changing functional behavior.
- `perf`: A code change that improves execution performance or memory usage.
- `chore`: Routine maintenance, dependencies, or tool configuration updates.
- `build`: Changes affecting build systems, packaging, or external tool dependencies.
- `ci`: Changes to CI/CD workflows and automated scripts.

#### Commit Best Practices:
- Keep commits **atomic and focused** on a single logical change.
- Write commit summaries in the **imperative mood** (e.g., `feat(estimation): add unscented kalman filter for soc`, NOT `added kalman filter`).
- Do not commit large binary artifacts, temporary datasets, or IDE caches.

---

## Section 17 — Code Review Standard

Before any pull request or module milestone is merged, it must undergo a thorough engineering review against this checklist:

- [ ] **Correctness**: Does the code accurately implement the required engineering logic and physics?
- [ ] **Architectural Compliance**: Does the code respect layer boundaries (Domain has no infrastructure dependencies)?
- [ ] **Battery/Hardware Agnosticism**: Are there any hardcoded assumptions regarding cell count, chemistry, or specific BMS hardware?
- [ ] **Type Safety**: Are all functions and classes strictly typed without untyped dictionaries or loose `Any` types?
- [ ] **Test Coverage**: Are unit and integration tests included with deterministic assertions?
- [ ] **Documentation**: Are docstrings complete with SI units, parameter descriptions, and clear rationale?
- [ ] **Code Quality**: Does the code pass `ruff check`, `ruff format`, and `mypy --strict` with zero errors?
- [ ] **Security**: Are all inputs validated and are there zero hardcoded secrets?
- [ ] **Performance**: Are there unnecessary allocations or logging statements in high-frequency loops?

---

## Section 18 — Definition of Done (DoD)

A development task or module is considered **DONE** only when all of the following criteria are satisfied:

1. **Complete Implementation**: The feature satisfies all specified functional and architectural requirements.
2. **Architectural Purity**: Adheres strictly to the 10 core architectural principles and layer boundaries.
3. **Fully Tested**: All relevant unit, integration, or simulation tests are written, passing, and deterministic.
4. **Type Checked**: Passes `mypy --strict` static type validation with zero errors.
5. **Linted & Formatted**: Passes `ruff check` and `ruff format --check` with zero warnings or errors.
6. **Documented**: Docstrings, architectural diagrams, and user-facing documentation are created or updated.
7. **No Technical Debt**: No commented-out code, temporary hacks, or unresolved TODOs left unaddressed.
8. **Approved Review**: Code review completed and validated against the engineering standards checklist.

*(Note: Documentation-only or configuration-only tasks must satisfy the documentation, linting, and review criteria).*

---

## Section 19 — Core Engineering Principles Summary

The **11 Cardinal Rules of TwinVolt Engineering**:

1. **Correctness Before Complexity**: Prioritize mathematical precision and software correctness over elaborate abstractions.
2. **Explicit Over Implicit**: Make data contracts, types, interfaces, and physical units explicitly visible in code.
3. **Strict Separation of Concerns**: Isolate domain physics, state estimation, ingestion adapters, storage, and visualization.
4. **Fail Safely & Predictably**: Validate all external inputs, handle sensor failures gracefully, and never fail silently.
5. **Universal & Parametric**: Build once, support many—never hardcode cell counts, chemistries, or hardware models into core logic.
6. **Decouple Models from Engine**: Treat PyBaMM, ECMs, and ML models as pluggable implementations behind common interfaces.
7. **Canonical Ingestion**: Always convert raw protocol data into canonical telemetry before processing.
8. **Inversion of Control**: High-level domain logic must never import low-level infrastructure drivers.
9. **Test Continuously & Deterministically**: Ensure every mathematical and estimation algorithm is verifiable with fixed-seed simulation suites.
10. **Zero Secrets in Git**: Enforce environment-based configuration and clean repository hygiene.
11. **No Premature Optimization or Abstraction**: Write clean, direct, and readable code; optimize only based on measured performance profiles.
