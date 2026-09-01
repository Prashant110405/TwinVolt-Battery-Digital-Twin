# TwinVolt — Configuration Management Architecture & Specifications

[![Status: Active Architecture Document](https://img.shields.io/badge/Architecture-Configuration-blue.svg)](#)
[![Compliance: Mandatory](https://img.shields.io/badge/Compliance-Mandatory-red.svg)](#)

---

## 1. Purpose & Scope

This document establishes the formal **Configuration Management Architecture, schemas, validation policies, and security boundaries** for the **TwinVolt Universal Battery Digital Twin Platform**.

TwinVolt is designed to be **universal, battery-agnostic, hardware-agnostic, and model-agnostic**. To support this mission without accumulating technical debt or architecture drift, all configuration—spanning software environments, battery profiles, physical hardware interfaces, mathematical models, and deployment infrastructure—must be strictly decoupled from business logic, deterministically validated, and securely handled.

---

## 2. Core Configuration Philosophy

TwinVolt adheres to five foundational configuration tenets:

1. **Declarative Over Imperative**: Configuration defines *what* a battery pack or runtime environment is, never *how* the software executes its algorithms.
2. **12-Factor App Compliance**: Strict separation between software source code, declarative configuration datasets, and environment-specific secrets.
3. **Boundary Validation (Fail-Fast)**: Configuration must be validated at the system boundary before instantiating internal domain objects or starting services.
4. **Zero Domain Ingestion of Raw Config**: Domain logic and physics engines never read configuration files, environment variables, or `.env` files directly. Validated parameters are passed via explicit dependency injection.
5. **Universal Battery Independence**: Battery configurations are external parametric datasets; no cell count, chemistry, or pack layout is baked into the codebase.

```text
┌────────────────────────────────────────────────────────────────────────┐
│                   Declarative Configuration Source                     │
│         (Environment Variables, YAML/JSON Battery Profiles)            │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                   System Boundary & Validation Layer                   │
│           (Pydantic Settings, Physical Range & Unit Checks)            │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ (Emits Validated Immutable Config)
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                      Domain Entity Factory                             │
│         (Constructs Pure Python Domain & Model Entities)               │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ (Injects Domain Objects)
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                      Digital Twin Core Engine                          │
│         (Executes Simulation, State Estimation & Telemetry Sync)       │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Configuration Categories

TwinVolt organizes configuration into five distinct, non-overlapping categories:

```text
                               ┌───────────────────────────┐
                               │    TwinVolt Config Root   │
                               └─────────────┬─────────────┘
          ┌──────────────────┬───────────────┼───────────────┬──────────────────┐
          ▼                  ▼               ▼               ▼                  ▼
┌──────────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────────┐
│   Application    │ │   Battery    │ │    Model     │ │Infrastructure│ │     Runtime      │
│  Configuration   │ │Configuration │ │Configuration │ │Configuration │ │  Configuration   │
└──────────────────┘ └──────────────┘ └──────────────┘ └──────────────┘ └──────────────────┘
```

### 3.1 Application Configuration
Governs the execution of the backend services, logging infrastructure, and web server behavior:
- **Environment Name**: `development`, `testing`, `staging`, `production`.
- **Service Identifiers**: Application name, service instance ID, version string.
- **Debug Flags**: Debug mode toggle, verbose error formatting.
- **Logging Settings**: Log level (`DEBUG`, `INFO`, `WARNING`, `ERROR`), log format (`json`, `console`), telemetry downsampling intervals.
- **Server Binding**: Host IP, HTTP port, CORS allowed origins, worker concurrency.

### 3.2 Battery Configuration
Declarative specification describing the physical, electrochemical, and operational boundaries of a battery system. 

> [!IMPORTANT]
> Battery configurations are **pure data contracts**, not application classes. They represent user-supplied parameters before the domain model interprets them.

Key conceptual properties:
- **Identification**: Unique battery profile ID, manufacturer, model name, serial metadata.
- **Electrochemical Chemistry**: Chemistry enum (e.g., `NMC`, `LFP`, `LCO`, `NCA`, `LTO`, `Sodium-Ion`).
- **Topology**: Total series cells ($N_s$), total parallel strings ($N_p$), total cell count ($N_{total} = N_s \times N_p$).
- **Electrical Ratings**: Nominal pack voltage, cell nominal voltage, total nominal capacity ($Ah$), total nominal energy ($Wh$).
- **Voltage Operational Limits**: Pack upper cutoff voltage ($V$), pack lower cutoff voltage ($V$), cell over-voltage threshold ($V$), cell under-voltage threshold ($V$).
- **Current Operational Limits**: Maximum continuous charge current ($A$), maximum continuous discharge current ($A$), peak pulse charge current ($A$), peak pulse discharge current ($A$).
- **Thermal Boundaries**: Minimum charging temperature ($^\circ C$), maximum charging temperature ($^\circ C$), minimum discharging temperature ($^\circ C$), maximum discharging temperature ($^\circ C$), thermal runaway warning threshold ($^\circ C$).
- **Balancing Parameters**: Cell-to-cell delta voltage balancing threshold ($mV$).

### 3.3 Model Configuration
Defines the mathematical modeling engines used by the Digital Twin Core for simulation, co-simulation, and state estimation:
- **Model Identifier**: Unique model instance identifier.
- **Model Class / Paradigm**:
  - `ECM_1RC`: 1-RC Thevenin Equivalent Circuit Model.
  - `ECM_2RC`: 2-RC Dual Polarization Equivalent Circuit Model.
  - `PHYSICS_PYBAMM_SPM`: Single Particle Model via PyBaMM backend.
  - `PHYSICS_PYBAMM_DFN`: Doyle-Fuller-Newman physics model via PyBaMM backend.
  - `DATA_DRIVEN_NEURAL`: Machine-learning empirical surrogate model.
  - `LOOKUP_TABLE`: Static OCV-SOC lookup table.
- **Model Parameters**: $R_0$ internal resistance ($\Omega$), $R_1, C_1, R_2, C_2$ polarization parameters, entropic heat coefficients, diffusion coefficients.
- **Solver & Time-Step Configuration**: Numerical solver type, integration step size ($\Delta t$ in milliseconds), convergence tolerance.

> [!NOTE]
> PyBaMM is **one supported model provider** among several. The configuration architecture must never assume PyBaMM is present or required.

### 3.4 Infrastructure Configuration
Defines connections to external datastores, message brokers, and networks:
- **Relational / Time-Series Database**: Host, port, database name, pool size, SSL mode.
- **In-Memory Cache & Streams (Redis)**: Host, port, DB index, connection timeout.
- **Telemetry Message Broker (MQTT)**: Broker host, port, client ID, base topic prefix, QoS level, keepalive interval.
- **Physical Communication Adapters**: Serial port name (`COM3` / `/dev/ttyUSB0`), baud rate (`115200`), CAN interface (`can0` / `vcan0`), CAN bitrate (`500000`).

### 3.5 Runtime Configuration
Defines dynamic execution modes without altering underlying battery or infrastructure definitions:
- **Execution Mode**: `live_hardware` (ingesting live physical BMS telemetry), `historical_replay` (replaying recorded datasets), `pure_simulation` (driving synthetic virtual load cycles).
- **Synthetic Generator Settings**: Standard drive cycle profile (`WLTP`, `US06`, `UDDS`, `CCCV_CHARGE`), noise injection standard deviation.
- **Feature Flags**: Dynamic state estimation enable/disable, thermal simulation enable/disable, cloud sync toggle.

---

## 4. Secrets Management & Zero-Leakage Policy

TwinVolt enforces strict separation between non-sensitive configuration parameters and confidential secrets.

```text
┌───────────────────────────────────┐       ┌───────────────────────────────────┐
│     Non-Sensitive Configuration   │       │         Sensitive Secrets         │
├───────────────────────────────────┤       ├───────────────────────────────────┤
│ • Battery chemistries & limits    │       │ • Database passwords              │
│ • Model time-step parameters      │       │ • MQTT broker passwords           │
│ • Hostnames, ports, log levels    │  VS   │ • API secret keys & JWT secrets   │
│ • Simulation drive-cycle names    │       │ • TLS private keys & certificates │
│ • Public broker topic names       │       │ • Hardware access tokens          │
├───────────────────────────────────┤       ├───────────────────────────────────┤
│ Stored in: YAML / Versioned Git   │       │ Stored in: Local .env / Vault / OS│
└───────────────────────────────────┘       └───────────────────────────────────┘
```

### 4.1 Strict Secrets Rules
1. **Never Commit Secrets to Version Control**: Passwords, API tokens, encryption keys, and private certificates must **never** be checked into Git.
2. **Local `.env` Isolation**: Real `.env` files are restricted to local machines and excluded via [.gitignore](file:///.gitignore).
3. **Template Placeholders Only**: [.env.example](file:///.env.example) contains safe, non-functional default placeholders only.
4. **No Secrets in Logs or Errors**: Log formatters and exception handlers must filter and sanitize sensitive fields (passwords, tokens, authorization headers).
5. **No Secrets in Domain Models**: Domain entities (e.g., `BatteryPack`, `Cell`) must never hold infrastructure credentials.

---

## 5. Configuration Precedence Model

When TwinVolt initializes, settings are resolved through a deterministic 4-tier hierarchy. Higher layers cleanly override lower layers:

```text
┌─────────────────────────────────────────────────────────────────────────┐
│  Tier 4: Runtime CLI Arguments & API Overrides (Highest Precedence)     │
│          (e.g., --log-level=DEBUG, dynamic simulation parameters)       │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │ Overrides
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  Tier 3: Environment Variables & Local .env                             │
│          (e.g., TWINVOLT_ENV=production, DB_PASSWORD=xxxx)              │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │ Overrides
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  Tier 2: Declarative Configuration Files                                │
│          (e.g., config/battery_profiles/nmc_3s.yaml, config/app.yaml)   │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │ Overrides
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  Tier 1: Built-in Code & Schema Defaults (Lowest Precedence)            │
│          (e.g., SIMULATION_STEP_MS = 100, LOG_LEVEL = "INFO")           │
└─────────────────────────────────────────────────────────────────────────┘
```

### 5.1 Resolution Flow
1. **Tier 1 (Built-in Defaults)**: Safe fallback constants defined within Pydantic schema field definitions.
2. **Tier 2 (Configuration Files)**: Structured YAML/JSON files specifying static battery definitions, model parameters, and application baselines.
3. **Tier 3 (Environment Variables)**: Environment variables matching designated prefixes (e.g., `TWINVOLT_`) or standard infrastructure names (e.g., `DB_HOST`) loaded at runtime.
4. **Tier 4 (Runtime Overrides)**: Direct command-line flags or authenticated runtime API payload overrides supplied during dynamic execution.

---

## 6. Validation Philosophy & Fail-Fast Integrity

Configuration errors in battery software can lead to physical safety hazards or silent algorithmic divergences. Configuration validation must be rigorous and fail immediately upon encountering invalid states.

### 6.1 Validation Rules
- **Required Fields**: Mandatory fields must be present; missing essential parameters must prevent startup.
- **Physical Boundaries**: Numerical values must reflect physical realities:
  - Voltage: $V > 0$ and $V_{min} < V_{nominal} < V_{max}$.
  - Capacity: $Capacity_{Ah} > 0$.
  - Resistance: $R_{internal} > 0$.
  - Temperature: $T > -273.15^\circ C$ (Absolute Zero).
- **Topology Integrity**: Cell count in series $N_s \ge 1$, parallel strings $N_p \ge 1$.
- **Enumerated Constraints**: Closed sets (e.g., chemistries, log levels, model types) must match strict enum values.
- **Distinct Exception Types**: Configuration validation failures must raise `ConfigurationValidationError` or `InvalidBatteryProfileError`, distinctly separating startup configuration errors from operational runtime crashes.

---

## 7. Units & Physical Quantities Standard

To eliminate ambiguity across international engineering teams, **all physical quantities must use explicit, standardized SI units**.

```text
┌────────────────────────┬───────────────────────┬────────────────────────┐
│ Physical Quantity      │ Canonical Unit        │ Field Naming Standard  │
├────────────────────────┼───────────────────────┼────────────────────────┤
│ Voltage                │ Volts (V)             │ *_v                    │
│ Millivolts             │ Millivolts (mV)       │ *_mv                   │
│ Current                │ Amperes (A)           │ *_a                    │
│ Capacity               │ Ampere-hours (Ah)     │ *_ah                   │
│ Energy                 │ Watt-hours (Wh)       │ *_wh                   │
│ Power                  │ Watts (W)             │ *_w                    │
│ Temperature            │ Celsius (°C)          │ *_c                    │
│ Temperature (Absolute) │ Kelvin (K)            │ *_k                    │
│ Resistance             │ Ohms (Ω)              │ *_ohm                  │
│ Internal Resistance    │ Milliohms (mΩ)        │ *_mohm                 │
│ Capacitance            │ Farads (F)            │ *_f                    │
│ Time / Duration        │ Seconds (s)           │ *_s                    │
│ Time / Interval        │ Milliseconds (ms)     │ *_ms                   │
└────────────────────────┴───────────────────────┴────────────────────────┘
```

> [!CRITICAL]
> **Never use bare, ambiguous field names** such as `"voltage": 3.7` or `"temp": 25`. Always use explicit suffixes: `"nominal_voltage_v": 3.7`, `"ambient_temp_c": 25.0`.

---

## 8. Battery Configuration vs. Domain Model Distinction

A fundamental architectural principle of TwinVolt is the **strict separation between Configuration Inputs and Domain Entities**.

```text
┌─────────────────────────────────────────────────────────────────────────┐
│                     Battery Configuration (Data Input)                  │
│  "What parameters did the user/file declare?"                           │
│  • Flat or nested serializable data structure (YAML/JSON/Dict).         │
│  • Contains raw numbers, strings, and unit-suffixed fields.             │
│  • Has no behavioral methods, state tracking, or active physics logic.  │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
                                     ▼ (Validation & Factory Instantiation)
┌─────────────────────────────────────────────────────────────────────────┐
│                      Battery Domain Model (Core Entity)                 │
│  "What does the battery represent inside TwinVolt?"                     │
│  • Rich, pure Python domain objects (`BatteryPack`, `CellModule`).      │
│  • Holds dynamic operational state (live voltages, SOC, SOH, temps).    │
│  • Provides business logic, invariant enforcement, and state queries.   │
└─────────────────────────────────────────────────────────────────────────┘
```

### The Unidirectional Initialization Pipeline
```text
Battery Profile File (.yaml) 
      ──► Validation Schema (Pydantic) 
      ──► Domain Factory 
      ──► BatteryPack Domain Object 
      ──► Twin Engine Co-Simulation
```

---

## 9. Schema Strategy & File Format

### 9.1 File Format: YAML & JSON
- **YAML (`.yaml` / `.yml`)**: The primary format for human-authored configuration (battery profiles, model parameter sets, application presets) due to its readability and support for comments.
- **JSON (`.json`)**: Fully supported for machine-generated configurations, API payloads, and automated export/import pipelines.

### 9.2 Validation Engine: Pydantic v2
- All configuration structures will be defined using **Pydantic v2** models (`pydantic-settings` and `pydantic.BaseModel`).
- Pydantic provides automatic type coercion, strict boundary validation, field documentation, and seamless export to JSON Schema.

---

## 10. Configuration Versioning & Migration Strategy

Configuration schemas will evolve as new battery models and features are added. Configuration files must never silently break due to schema changes.

### 10.1 Versioning Rules
1. **Mandatory Schema Version**: Every declarative configuration file must specify a `schema_version` attribute:
   ```yaml
   schema_version: "1.0"
   ```
2. **Semantic Versioning for Schemas**:
   - **Patch (`1.0.1`)**: Adding optional fields with default values (fully backward-compatible).
   - **Minor (`1.1.0`)**: Deprecating fields or adding new non-breaking features.
   - **Major (`2.0.0`)**: Breaking structure changes, requiring explicit configuration migration.
3. **Graceful Migration**: Configuration loaders must detect schema versions and pass legacy configurations through schema migration adapters when necessary.

---

## 11. Environment Separation

TwinVolt operates identically across environments by swapping configuration rather than modifying application code.

```text
┌──────────────────┐  Loads  ┌──────────────────────────────────────────────┐
│   Development    │ ──────► │ Local .env, SQLite / Docker DB, Mock Telemetry│
├──────────────────┤         ├──────────────────────────────────────────────┤
│   Testing / CI   │ ──────► │ In-Memory Mocks, Fast Synthetic Drive Cycles │
├──────────────────┤         ├──────────────────────────────────────────────┤
│   Staging        │ ──────► │ Staging TimescaleDB, Replay Telemetry Feed   │
├──────────────────┤         ├──────────────────────────────────────────────┤
│   Production     │ ──────► │ Clustered TimescaleDB, Live Hardware MQTT/CAN│
└──────────────────┘         └──────────────────────────────────────────────┘
```

- Code must never contain conditional environment checks like `if environment == "production": do_x()`.
- Environment-specific behaviors must be driven by explicit configuration flags (e.g., `enable_realtime_estimation`, `mock_telemetry_enabled`).

---

## 12. Architectural Boundaries & Isolation Rules

The following **10 Mandatory Isolation Rules** govern all configuration usage across TwinVolt:

1. **Domain Code Isolation**: Pure domain code (`src/domain/`) must **NEVER** import `os`, `dotenv`, or read environment variables directly.
2. **No Direct Filesystem Access in Domain**: Domain entities must never perform filesystem I/O to read configuration files.
3. **No Infrastructure Leakage**: Database connection strings, broker URLs, and port numbers must never appear in domain models or battery profiles.
4. **No UI Settings in Battery Profiles**: Battery profile definitions must not contain UI layout, color, or dashboard widget settings.
5. **No Physics in UI Configuration**: Frontend configuration must never define mathematical battery equations or physics constants.
6. **No Model-Infrastructure Entanglement**: Model parameter sets must not control database retention policies or message queue configurations.
7. **Secrets Segregation**: Sensitive credentials must remain outside standard domain configuration objects.
8. **Boundary Ingestion Only**: Configuration parsing and environment loading belong strictly at the application entry points (`src/api/`, `scripts/`, `src/adapters/`).
9. **Explicit Constructor Injection**: Validated configuration parameters must be passed to core domain objects via explicit constructor arguments or factory methods.
10. **Immutable Runtime Config**: Once loaded and validated at service startup, application configuration objects should be treated as immutable (`frozen=True`).

---

## 13. Security Standards for Configuration

1. **Untrusted Configuration Principle**: Configuration files supplied by users or external APIs must be treated as untrusted input and subjected to schema validation before parsing.
2. **Safe Deserialization**: YAML files must **always** be parsed using safe loaders (`yaml.safe_load()`). Unsafe execution loaders (`yaml.load()` or `pickle.loads()`) are strictly forbidden.
3. **No Dynamic Code Execution**: Configuration files must never contain executable code, lambda expressions, or dynamic class paths.
4. **Least Privilege Credentials**: Infrastructure configuration (PostgreSQL, MQTT) must use credentials scoped with minimal necessary permissions.

---

## 14. Examples: GOOD vs. BAD Configuration Practices

### Example 1: Battery Profile Specification

#### ❌ BAD (Ambiguous, hardcoded, untyped, missing units, no versioning)
```yaml
# BAD: What chemistry? What units? What schema version?
battery:
  name: "pack1"
  cells: 3
  v_nom: 11.1
  v_max: 12.6
  cap: 2200
  temp_limit: 45
```

#### ✅ GOOD (Explicit, typed, versioned, unambiguous SI units)
```yaml
# GOOD: Explicit schema version, unambiguous units, validated chemistry
schema_version: "1.0"
battery_profile:
  profile_id: "batt-nmc-18650-3s1p-v1"
  display_name: "NMC 18650 3S1P Reference Pack"
  chemistry: "NMC"
  topology:
    series_count: 3
    parallel_count: 1
    total_cells: 3
  ratings:
    nominal_pack_voltage_v: 11.1
    nominal_cell_voltage_v: 3.7
    nominal_capacity_ah: 2.2
    nominal_energy_wh: 24.42
  voltage_limits:
    cell_min_cutoff_v: 3.0
    cell_max_cutoff_v: 4.2
    pack_min_cutoff_v: 9.0
    pack_max_cutoff_v: 12.6
  current_limits:
    max_continuous_charge_a: 2.2
    max_continuous_discharge_a: 4.4
    peak_pulse_discharge_a: 10.0
  thermal_limits:
    min_charge_temp_c: 0.0
    max_charge_temp_c: 45.0
    min_discharge_temp_c: -20.0
    max_discharge_temp_c: 60.0
    thermal_warning_temp_c: 50.0
```

---

### Example 2: Model Configuration

#### ❌ BAD (Hardcoded directly to one modeling backend, missing solver config)
```yaml
# BAD: Hardcoded to PyBaMM with untyped parameters
model:
  pybamm_model: "DFN"
  res: 0.05
```

#### ✅ GOOD (Decoupled paradigm, explicit solver settings, SI units)
```yaml
# GOOD: Explicit model paradigm, provider-agnostic parameter contract
schema_version: "1.0"
model_configuration:
  model_id: "ecm-2rc-nmc-standard"
  paradigm: "ECM_2RC"
  description: "Dual Polarization Equivalent Circuit Model for NMC cells"
  sampling:
    simulation_step_ms: 100
    solver_type: "explicit_rk4"
  parameters:
    series_resistance_r0_mohm: 25.0
    rc1_resistance_r1_mohm: 15.0
    rc1_capacitance_c1_f: 1200.0
    rc2_resistance_r2_mohm: 10.0
    rc2_capacitance_c2_f: 4500.0
```

---

## 15. Future Architectural Review Items

As TwinVolt matures into production deployment, the following configuration enhancements will be formally evaluated in future Architecture Decision Records (ADRs):

1. **Dynamic Runtime Parameter Reconfiguration**: Evaluating which model parameters (e.g., Kalman filter process noise covariance $Q$, measurement noise covariance $R$) can be updated dynamically via authenticated API without requiring full service restarts.
2. **Distributed Configuration Registries**: Evaluating centralized key-value stores (e.g., Consul, etcd) for multi-tenant, fleet-scale Digital Twin deployments.
3. **Automated Schema Code Generation**: Evaluating tooling to automatically generate TypeScript frontend schema definitions directly from Pydantic backend models.
