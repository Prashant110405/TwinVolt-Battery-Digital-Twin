# TwinVolt — Error Handling & Logging Architecture

[![Status: Active Architecture Document](https://img.shields.io/badge/Architecture-Error%20Handling%20%26%20Logging-blue.svg)](#)
[![Compliance: Mandatory](https://img.shields.io/badge/Compliance-Mandatory-red.svg)](#)

---

## Document Overview & Purpose

This document establishes the formal **error handling architecture, exception propagation rules, fail-safe mechanisms, structured logging conventions, and observability standards** for the **TwinVolt Universal Battery Digital Twin Platform**.

TwinVolt operates at the intersection of high-frequency physical telemetry, electrochemical simulation, state estimation filters, and distributed backend services. In safety-critical battery engineering, errors must be captured with rich diagnostic context, handled predictably at architectural boundaries, and logged without compromising system performance or leaking sensitive data.

---

## Table of Contents

1. [Part 1 — Error Handling Philosophy](#part-1--error-handling-philosophy)
2. [Part 2 — Conceptual Error Categories](#part-2--conceptual-error-categories)
3. [Part 3 — Error Boundaries & Layer Isolation](#part-3--error-boundaries--layer-isolation)
4. [Part 4 — Recoverable vs. Non-Recoverable Errors](#part-4--recoverable-vs-non-recoverable-errors)
5. [Part 5 — Retry Policy & Backoff Principles](#part-5--retry-policy--backoff-principles)
6. [Part 6 — Fail-Safe Philosophy in Battery Engineering](#part-6--fail-safe-philosophy-in-battery-engineering)
7. [Part 7 — Error Context & Diagnostic Metadata](#part-7--error-context--diagnostic-metadata)
8. [Part 8 — Logging Levels & Semantic Guidelines](#part-8--logging-levels--semantic-guidelines)
9. [Part 9 — Structured Logging Specification](#part-9--structured-logging-specification)
10. [Part 10 — High-Frequency Telemetry Stream Logging Rules](#part-10--high-frequency-telemetry-stream-logging-rules)
11. [Part 11 — Security & Privacy in Logging](#part-11--security--privacy-in-logging)
12. [Part 12 — External Input Validation & Sanitization](#part-12--external-input-validation--sanitization)
13. [Part 13 — Exception Propagation & Translation Strategy](#part-13--exception-propagation--translation-strategy)
14. [Part 14 — User-Facing vs. Internal Diagnostic Errors](#part-14--user-facing-vs-internal-diagnostic-errors)
15. [Part 15 — Error Code Scheme & Taxonomy Strategy](#part-15--error-code-scheme--taxonomy-strategy)
16. [Part 16 — Observability Architecture: Logs, Metrics & Traces](#part-16--observability-architecture-logs-metrics--traces)
17. [Part 17 — Digital Twin-Specific Failure Scenarios](#part-17--digital-twin-specific-failure-scenarios)
18. [Part 18 — Operational Error Severity Matrix](#part-18--operational-error-severity-matrix)
19. [Part 19 — Testing Requirements for Errors & Logging](#part-19--testing-requirements-for-errors--logging)
20. [Part 20 — 10 Mandatory Architectural Rules](#part-20--10-mandatory-architectural-rules)
21. [Part 21 — Conceptual Implementation Architecture](#part-21--conceptual-implementation-architecture)
22. [Architectural Decisions for Future Review](#architectural-decisions-for-future-review)

---

## Part 1 — Error Handling Philosophy

TwinVolt adheres to eight foundational error handling tenets:

1. **Fail Explicitly on Invariant Violations**: When physical limits, mathematical consistency, or architectural constraints are violated, the system must fail immediately and loudly rather than propagating corrupted state.
2. **Zero Silent Failures**: Never suppress errors or swallow exceptions with empty `except:` or `pass` blocks. Every handled error must result in a deliberate recovery action, state transition, metric increment, or log entry.
3. **Rich Diagnostic Context**: Errors must carry sufficient context (e.g., component, operation, timestamp, entity ID) to enable deterministic post-mortem diagnosis.
4. **Clean Boundary Separation**: Low-level infrastructure exceptions (network timeouts, SQL errors) must not pollute the pure domain layer.
5. **No Exceptions for Normal Control Flow**: Exceptions must represent truly exceptional or erroneous conditions, not standard algorithmic branches (e.g., checking if a cache key exists).
6. **Input Validation at Boundaries**: Data is validated upon entering the system before touching internal domain models.
7. **Sanitized User Exposure**: Technical stack traces and internal topologies must never be leaked to public API clients.
8. **Fail-Safe Battery State Representation**: If an algorithm cannot compute a reliable battery state, it must mark the estimate as unavailable rather than fabricating synthetic approximations.

```text
┌─────────────────────────────────────────────────────────────────────────┐
│                           Error Triage Flow                             │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
                        Is the error recoverable?
                                ├── YES ──► Execute bounded retry / fallback ──► Log WARNING / Metric
                                └── NO
                                     │
                        Is it at a system boundary?
                                ├── YES ──► Translate to sanitized API error ──► Log ERROR / CRITICAL
                                └── NO  ──► Attach contextual metadata ───────► Propagate up the stack
```

---

## Part 2 — Conceptual Error Categories

TwinVolt organizes future errors into ten distinct operational domains:

```text
                               ┌───────────────────────────┐
                               │     TwinVolt Error Tree   │
                               └─────────────┬─────────────┘
          ┌──────────────────┬───────────────┼───────────────┬──────────────────┐
          ▼                  ▼               ▼               ▼                  ▼
┌──────────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────────┐
│  Configuration   │ │  Validation  │ │    Domain    │ │    Model     │ │ Telemetry / Data │
│      Errors      │ │    Errors    │ │    Errors    │ │    Errors    │ │      Errors      │
└──────────────────┘ └──────────────┘ └──────────────┘ └──────────────┘ └──────────────────┘
          ▼                  ▼               ▼               ▼                  ▼
┌──────────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────────┐
│  Communication   │ │Infrastructure│ │   Storage    │ │Authentication│ │    Internal /    │
│      Errors      │ │    Errors    │ │    Errors    │ │& Sec Errors  │ │Unexpected Errors │
└──────────────────┘ └──────────────┘ └──────────────┘ └──────────────┘ └──────────────────┘
```

1. **Configuration Errors**: Missing required configuration keys, malformed YAML/JSON profiles, unparseable environment variables, or schema version mismatches.
2. **Validation Errors**: Out-of-bounds parameters (e.g., negative cell capacity, negative resistance, invalid chemistry string).
3. **Domain Errors**: Domain invariant breaches (e.g., requesting cell index 4 in a 3S pack, invalid state transition).
4. **Model Errors**: Numerical divergence in differential equation solvers (e.g., PyBaMM DFN solver failure, singular matrix in Kalman filter matrix inversion).
5. **Telemetry / Data Errors**: Malformed canonical telemetry, CRC frame errors, out-of-order timestamps, or corrupted sensor payloads.
6. **Communication Errors**: MQTT broker disconnections, serial port timeouts, CAN bus off-state, or dropped WebSocket connections.
7. **Infrastructure Errors**: Container startup failures, thread pool exhaustion, or memory allocation limits.
8. **Storage Errors**: PostgreSQL query timeouts, TimescaleDB chunk creation errors, or Redis connection drops.
9. **Authentication & Security Errors**: Invalid API tokens, unauthorized pack access, or untrusted payload rejection.
10. **Internal / Unexpected Errors**: Unhandled runtime exceptions indicating software bugs (e.g., `AssertionError`, unexpected `NoneType`).

---

## Part 3 — Error Boundaries & Layer Isolation

To prevent architectural coupling, exceptions must respect layer boundaries through Inversion of Control.

```text
┌─────────────────────────────────────────────────────────────────────────┐
│                           External Client / UI                          │
└────────────────────────────────────▲────────────────────────────────────┘
                                     │ (Sanitized API Error Payload)
┌────────────────────────────────────┴────────────────────────────────────┐
│                    Application / API Boundary Layer                     │
│    (Translates Internal Exceptions -> Clean HTTP / WS Error Responses)  │
└────────────────────────────────────▲────────────────────────────────────┘
                                     │ (Domain & Application Exceptions)
┌────────────────────────────────────┴────────────────────────────────────┐
│                       Digital Twin Core Engine                          │
│               (State Sync, Estimators, Model Orchestration)             │
└────────────────────────────────────▲────────────────────────────────────┘
                                     │ (Canonical Telemetry / Domain Errors)
┌────────────────────────────────────┴────────────────────────────────────┐
│                   Data Ingestion & Adapters Layer                       │
│    (Catches Driver / Protocol Errors -> Emits Canonical Anomaly Events) │
└─────────────────────────────────────────────────────────────────────────┘
```

### Boundary Isolation Rules:
- **No Infrastructure Leaks into Domain**: A `paho.mqtt.MQTTException` or `psycopg2.OperationalError` must **never** propagate directly into the core domain layer. The ingestion adapter or repository must catch, log, and translate low-level driver exceptions into standardized domain or application errors.
- **Pure Domain Exception Contracts**: The Battery Domain defines its own error types. It has zero awareness of HTTP status codes, SQL error numbers, or network socket states.

---

## Part 4 — Recoverable vs. Non-Recoverable Errors

The operational handling of an error depends on whether the system can autonomously recover without human intervention or data corruption.

```text
┌──────────────────────────────────────────────┬──────────────────────────────────────────────┐
│             Recoverable Errors               │           Non-Recoverable Errors             │
├──────────────────────────────────────────────┼──────────────────────────────────────────────┤
│ • Transient MQTT broker disconnection        │ • Invalid battery chemistry configuration    │
│ • Database connection pool exhaustion        │ • Physical impossible parameters (e.g. V < 0)│
│ • Occasional dropped telemetry packet        │ • Corrupted unparseable model parameter set  │
│ • Temporary REST timeout from remote logger  │ • Unsupported configuration schema version   │
│ • Single sensor noise spike (filtered out)   │ • Fatal domain invariant violation           │
├──────────────────────────────────────────────┼──────────────────────────────────────────────┤
│ Action: Bounded Retry, Fallback, Reconnect   │ Action: Fail-Fast Startup Halt, Reject Task  │
└──────────────────────────────────────────────┴──────────────────────────────────────────────┘
```

> [!NOTE]
> Context determines recoverability. A dropped packet during continuous 100 Hz streaming is recoverable (the filter extrapolates); a missing battery profile at system boot is strictly non-recoverable.

---

## Part 5 — Retry Policy & Backoff Principles

Automated retries must be carefully governed to prevent cascading failure and system exhaustion.

### Core Retry Principles:
1. **Idempotency Requirement**: Retries are permitted **only** for idempotent operations (e.g., read queries, telemetry polling, stateless socket reconnects). State-mutating operations must not be retried without idempotency keys.
2. **Bounded Retry Count**: Every retry mechanism must have a strict upper limit (e.g., maximum 3 to 5 attempts). Infinite retry loops are strictly forbidden.
3. **Exponential Backoff with Jitter**: Retries must incorporate exponential backoff with randomized jitter to prevent synchronized retry storms:
   $$\text{Delay} = \min(\text{MaxDelay}, \text{BaseDelay} \times 2^{\text{attempt}}) \pm \text{RandomJitter}$$
4. **Fast-Fail on Permanent Errors**: Retries must **never** be executed on permanent client/configuration errors (e.g., HTTP 400 Bad Request, schema validation failure, invalid battery ID).

---

## Part 6 — Fail-Safe Philosophy in Battery Engineering

Battery Digital Twins model electro-thermal dynamics where inaccurate estimations can lead to dangerous thermal events or degraded battery life.

```text
       UNSAFE (Fabrication)                              SAFE (Fail-Safe)
┌──────────────────────────────────────┐          ┌──────────────────────────────────────┐
│ # BAD: Inaccurate / Fabricated State │          │ # GOOD: Explicit Unavailability      │
│ if kalman_filter_diverged:           │          │ if kalman_filter_diverged:           │
│     soc = 0.50  # Guessing 50%       │   VS     │     soc_estimate.is_valid = False    │
│                                      │          │     soc_estimate.error_code = "DIV"  │
│ if temp_sensor_failed:               │          │ if temp_sensor_failed:               │
│     temp = 25.0 # Fabricating 25°C   │          │     raise SensorFaultError(...)      │
└──────────────────────────────────────┘          └──────────────────────────────────────┘
```

### Safety Rules:
1. **No Data Fabrication**: If an estimation algorithm (e.g., EKF/UKF SOC estimator) fails to converge or receives invalid inputs, it must **never fabricate an arbitrary state value**.
2. **Explicit State Validity Flags**: State estimations must expose explicit validity indicators (`is_valid: bool`, `confidence_interval: float`, `status: Enum`).
3. **Sensor Anomaly Isolation**: Impossible sensor measurements (e.g., cell voltage $> 5.0\text{V}$ for NMC, cell temperature $> 120^\circ\text{C}$ during ambient rest) must be flagged as sensor faults and prevented from corrupting the core twin model state.

---

## Part 7 — Error Context & Diagnostic Metadata

When an error occurs, capturing sufficient diagnostic metadata is essential for debugging without compromising security.

### Standard Error Context Attributes:
- **`timestamp`**: UTC timestamp of the error event in ISO 8601 format.
- **`component`**: Subsystem emitting the error (e.g., `adapters.mqtt`, `estimation.ekf_soc`).
- **`operation`**: Specific function or pipeline step being executed (e.g., `parse_can_frame`, `solve_step`).
- **`error_category`**: Standard category classification.
- **`correlation_id` / `request_id`**: Trace identifier tracking the data flow across asynchronous tasks.
- **`battery_id` / `twin_id`**: Associated battery pack or digital twin instance.
- **`details`**: Non-sensitive contextual parameters (e.g., `{"cell_index": 2, "observed_v": 4.85, "limit_v": 4.2}`).

> [!CAUTION]
> **Zero Secrets in Error Context**: Passwords, API tokens, MQTT credentials, and database connection strings must **never** be attached to error context dictionaries or exception messages.

---

## Part 8 — Logging Levels & Semantic Guidelines

TwinVolt establishes clear semantic definitions for logging levels to maintain signal-to-noise ratio:

| Level | Semantic Definition | Permitted Usage Examples |
| :--- | :--- | :--- |
| **`DEBUG`** | High-volume diagnostic information intended for developers during active troubleshooting. | • Matrix condition numbers during solver iteration<br>• Decoded raw payload bytes<br>• Internal state transition calculations |
| **`INFO`** | Normal operational milestones and major lifecycle state transitions. | • Service / Twin startup and graceful shutdown<br>• Battery profile loaded successfully<br>• Ingestion adapter connected to MQTT broker |
| **`WARNING`** | Unexpected or degraded situations that were handled gracefully without failing the operation. | • Dropped single telemetry packet in high-frequency stream<br>• Sensor reading outlier replaced by estimator fallback<br>• Telemetry latency jitter exceeding nominal threshold |
| **`ERROR`** | Significant operational failures affecting a specific request, computation, or connection. | • Failed to parse a batch of CAN telemetry frames<br>• State estimator divergence on a valid telemetry feed<br>• Database write failure for historical time-series batch |
| **`CRITICAL`** | Severe conditions threatening system integrity, data corruption, or physical safety alerts. | • Detected thermal runaway precursor ($dT/dt > 1.5\text{ K/s}$)<br>• Irrecoverable configuration corruption during boot<br>• Storage disk full / process out-of-memory |

---

## Part 9 — Structured Logging Specification

In production, TwinVolt requires **structured, machine-readable JSON logging** to facilitate automated log aggregation, filtering, and metric extraction.

```json
{
  "timestamp": "2026-08-31T22:20:00.123Z",
  "level": "ERROR",
  "logger": "twinvolt.estimation.ekf_soc",
  "message": "EKF numerical divergence detected during measurement update step",
  "twin_id": "twin-nmc-pack-01",
  "battery_id": "batt-nmc-18650-3s1p",
  "correlation_id": "req-8f92a10b-5c4d",
  "error_category": "MODEL_ERROR",
  "details": {
    "step_index": 1420,
    "covariance_trace": 14502.8,
    "current_a": -2.5,
    "terminal_v": 11.2
  }
}
```

- **Standard Field Keys**: Standard keys (`timestamp`, `level`, `logger`, `message`, `twin_id`, `correlation_id`) must remain consistent across all modules.
- **Context Binding**: Loggers should support context binding (e.g., binding `twin_id` at session start) rather than requiring manual parameter repetition in every log call.

---

## Part 10 — High-Frequency Telemetry Stream Logging Rules

TwinVolt will ingest telemetry streams at rates up to 100 Hz. **Unconstrained logging in high-frequency loops causes CPU starvation, disk saturation, and massive log bloat.**

```text
                               100 Hz Telemetry Stream
                                         │
                                         ▼
                 ┌───────────────────────────────────────────────┐
                 │       High-Frequency Ingestion Loop           │
                 └───────────────────────┬───────────────────────┘
                                         │
                         Is log level set to DEBUG?
                                ├── YES ──► Emit diagnostic log (Development only)
                                └── NO
                                         │
                         Is there an anomaly or fault?
                                ├── YES ──► Emit WARNING / ERROR log
                                └── NO
                                         │
                         Periodic Summary / Downsampled Metric (e.g. 1 Hz)
                                         │
                                         ▼
                            Emit Aggregated Metrics / Health
```

### High-Frequency Logging Rules:
1. **Never Log Individual Telemetry Frames at INFO**: Emitting an `INFO` log for every voltage/current sample at 100 Hz is strictly prohibited.
2. **Use Metric Counters & Gauges**: Track ingested packet counts, average throughput, and frame loss rates via in-memory metrics rather than disk logs.
3. **Log by Exception Only**: In steady-state streaming, log only when an anomaly, CRC error, dropped connection, or safety threshold violation occurs.
4. **Downsampled Periodic Heartbeats**: If heartbeat logging is required, emit a single aggregated summary log at a low rate (e.g., once every 60 seconds).

---

## Part 11 — Security & Privacy in Logging

Logs are frequently stored in centralized search systems (e.g., Elasticsearch, CloudWatch). Security and credential hygiene are paramount.

### Strict Redaction Rules:
1. **Strictly Prohibited Log Fields**:
   - `password`, `db_password`, `mqtt_password`
   - `secret_key`, `api_key`, `jwt_token`, `auth_header`
   - `private_key`, `tls_key`, `certificate_passphrase`
2. **Sanitize Network Strings**: Redact embedded credentials in connection URIs (e.g., log `postgresql://user:***@localhost:5432/db` instead of the raw URI).
3. **Sensitive Metadata Redaction**: Mask or hash sensitive user-identifying information where applicable in shared environments.

---

## Part 12 — External Input Validation & Sanitization

All data originating outside the core process boundary is considered **untrusted external input**.

```text
┌─────────────────────────────────────────────────────────────────────────┐
│              Raw External Ingestion (MQTT, CAN, REST, Serial)           │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │ (Untrusted Payload)
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                   Schema Validation & Sanitization                      │
│            (Pydantic / Boundary Validator: Range & Type Checks)         │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │ (Emits Validated Canonical Telemetry)
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      Digital Twin Core & Domain Engine                  │
└─────────────────────────────────────────────────────────────────────────┘
```

- Ingestion adapters must decode raw network/serial packets and validate them against strongly typed schema contracts before passing them to the core domain.
- Malformed frames must be dropped at the adapter level with an incremented error counter, isolating the core twin from corruption.

---

## Part 13 — Exception Propagation & Translation Strategy

Exceptions should propagate naturally through internal domain logic and be translated at architectural boundaries:

```text
Low-Level Infrastructure Driver (e.g. Socket / Serial / Database)
        │ (Catches driver-specific error)
        ▼
Adapter / Repository Layer
        │ (Translates to unified Domain / Application Exception)
        ▼
Application / Orchestration Service
        │ (Executes recovery or handles transaction rollback)
        ▼
API / Interface Boundary
        │ (Translates to sanitized user-facing error response)
        ▼
External Client
```

- **Avoid Redundant Translation**: Do not wrap exceptions at every single function call. Only translate exceptions across major architectural layer boundaries (e.g., Driver -> Domain, Domain -> REST API).

---

## Part 14 — User-Facing vs. Internal Diagnostic Errors

TwinVolt enforces a clear distinction between internal engineering diagnostics and user-facing API error responses.

```text
┌─────────────────────────────────────────────────────────────────────────┐
│                   Internal Diagnostic Log (Engineering)                 │
├─────────────────────────────────────────────────────────────────────────┤
│ [ERROR] PostgreSQL connection failed: connection to server at           │
│ "10.0.4.12", port 5432 failed: FATAL: password authentication failed    │
│ for user "twinvolt_core"                                                │
└─────────────────────────────────────────────────────────────────────────┘
                                    VS
┌─────────────────────────────────────────────────────────────────────────┐
│                  User-Facing API Response (Sanitized)                   │
├─────────────────────────────────────────────────────────────────────────┤
│ HTTP/1.1 503 Service Unavailable                                       │
│ Content-Type: application/json                                          │
│                                                                         │
│ {                                                                       │
│   "error_code": "STORAGE_UNAVAILABLE",                                  │
│   "message": "The telemetry storage service is temporarily unavailable.",│
│   "correlation_id": "req-8f92a10b-5c4d",                                │
│   "timestamp": "2026-08-31T22:20:00Z"                                   │
│ }                                                                       │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Part 15 — Error Code Scheme & Taxonomy Strategy

To support frontend localization, automated API error handling, and structured telemetry alerting, TwinVolt will adopt a structured error code taxonomy.

### Conceptual Taxonomy Format:
$$\text{CATEGORY}\_\text{REASON}$$

Examples:
- `CONFIG_INVALID_SCHEMA_VERSION`
- `CONFIG_PHYSICAL_RANGE_ERROR`
- `TELEMETRY_TIMESTAMP_DISCONTINUITY`
- `TELEMETRY_FRAME_CORRUPTED`
- `MODEL_CONVERGENCE_FAILED`
- `ESTIMATION_STATE_UNAVAILABLE`
- `ADAPTER_CONNECTION_TIMEOUT`
- `AUTH_TOKEN_EXPIRED`

> [!NOTE]
> The full error-code catalog will be defined incrementally as domain and adapter milestones are implemented.

---

## Part 16 — Observability Architecture: Logs, Metrics & Traces

TwinVolt treats observability as a four-pillar framework:

```text
┌─────────────────────────────────────────────────────────────────────────┐
│                     TwinVolt Observability Pillars                      │
├───────────────────┬───────────────────┬────────────────┬────────────────┤
│    1. Logging     │    2. Metrics     │   3. Tracing   │4. Health Checks│
├───────────────────┼───────────────────┼────────────────┼────────────────┤
│ Discrete discrete │ Continuous time-  │ Distributed    │ Real-time      │
│ event records     │ series numeric    │ request flow   │ operational    │
│ with rich textual │ aggregates        │ across async   │ readiness &    │
│ context & error   │ (counters, rates, │ queues & API   │ liveness       │
│ stack traces.     │ latencies).       │ workers.       │ probes.        │
└───────────────────┴───────────────────┴────────────────┴────────────────┘
```

- **Health Checks**: Standardized `/health/live` (process is alive) and `/health/ready` (adapters connected, database accessible) endpoints.
- **Telemetry Quality Indicators**: Tracking packet loss percentage, timestamp jitter, and out-of-range sample counts.

---

## Part 17 — Digital Twin-Specific Failure Scenarios

Battery Digital Twins encounter unique domain failure modes that must be handled distinctly:

```text
┌──────────────────────────────────────┬──────────────────────────────────────────────────────────┐
│ Failure Scenario                     │ Required Handling & State Behavior                       │
├──────────────────────────────────────┼──────────────────────────────────────────────────────────┤
│ 1. Timestamp Discontinuity           │ Detect packet gap; if $\Delta t > t_{max}$, reset        │
│    (e.g., dropped packets > 5s)      │ numerical integration step; log WARNING.                 │
├──────────────────────────────────────┼──────────────────────────────────────────────────────────┤
│ 2. Sensor Outlier / Noise Spike      │ Statistical outlier rejection ($3\sigma$ residual test); │
│    (e.g., momentary 0V reading)      │ Kalman filter ignores outlier; state remains stable.     │
├──────────────────────────────────────┼──────────────────────────────────────────────────────────┤
│ 3. Missing Measurement               │ Use model prediction step without measurement update;    │
│    (e.g., temperature sensor dropout)│ flag thermal state confidence as degraded.               │
├──────────────────────────────────────┼──────────────────────────────────────────────────────────┤
│ 4. Model Numerical Divergence        │ Catch solver divergence; fall back to 1-RC ECM or OCV    │
│    (e.g., PyBaMM stiff ODE failure)  │ lookup table; flag model status as degraded.             │
├──────────────────────────────────────┼──────────────────────────────────────────────────────────┤
│ 5. Battery Configuration Mismatch    │ Detect cell count mismatch between telemetry stream and  │
│    (e.g., 3S telemetry on 4S config) │ profile; halt twin initialization immediately; ERROR.    │
└──────────────────────────────────────┴──────────────────────────────────────────────────────────┘
```

---

## Part 18 — Operational Error Severity Matrix

Error severity reflects operational and safety impact rather than arbitrary exception class hierarchy:

```text
┌──────────────┬──────────────────────────────────────────┬───────────────────────────────────────┐
│ Severity     │ Operational & Safety Impact              │ Required Response                     │
├──────────────┼──────────────────────────────────────────┼───────────────────────────────────────┤
│ **LOW**      │ Minor transient anomaly; zero data loss. │ Log DEBUG / WARNING; increment metric.│
├──────────────┼──────────────────────────────────────────┼───────────────────────────────────────┤
│ **MEDIUM**   │ Degraded estimation or missing optional  │ Log WARNING; fall back to secondary   │
│              │ telemetry; twin continues operating.     │ estimator; notify dashboard.          │
├──────────────┼──────────────────────────────────────────┼───────────────────────────────────────┤
│ **HIGH**     │ Loss of telemetry feed, persistent model │ Log ERROR; mark twin state as stale;  │
│              │ divergence, or database write failure.   │ trigger operator alert.               │
├──────────────┼──────────────────────────────────────────┼───────────────────────────────────────┤
│ **CRITICAL** │ Thermal runaway precursor, over-voltage, │ Log CRITICAL; raise safety alert;     │
│              │ or irrecoverable system corruption.      │ halt charging/simulation if coupled.  │
└──────────────┴──────────────────────────────────────────┴───────────────────────────────────────┘
```

---

## Part 19 — Testing Requirements for Errors & Logging

Error handling and logging pathways must be verified with automated tests during implementation:

1. **Negative Validation Tests**: Verify that invalid configurations and corrupted telemetry payloads are rejected with explicit, predictable error types.
2. **Bounded Retry Verification**: Test that retry decorators terminate strictly after the configured maximum attempts with exponential backoff.
3. **Secret Redaction Tests**: Automated assertions verifying that logs and serialized error outputs never contain test passwords or tokens.
4. **Fail-Safe Fallback Tests**: Verify that model divergence triggers graceful estimator degradation without crashing the twin execution loop.
5. **High-Frequency Performance Benchmarks**: Verify that logging at `INFO` under sustained 100 Hz telemetry does not introduce measurable latency overhead.

---

## Part 20 — 10 Mandatory Architectural Rules

1. **Domain Isolation**: Pure domain logic must remain completely independent of external logging frameworks (`structlog`, `loguru`) and web frameworks.
2. **No Infrastructure Exception Leaks**: Low-level driver exceptions must be translated at adapter boundaries.
3. **No Silent Error Swallowing**: Every exception must be handled deliberately, logged, or propagated.
4. **Never Fabricate Battery State**: Inaccurate or uncomputable states must be marked as invalid/unavailable.
5. **Boundary Input Validation**: All incoming external telemetry must be validated before entering core logic.
6. **Zero Credentials in Logs**: Sensitive secrets, keys, and tokens must never appear in logs or error messages.
7. **Bounded Retries Only**: Infinite retry loops are strictly prohibited.
8. **No High-Frequency Log Spam**: High-frequency streaming telemetry must use metrics counters and exception-only logging.
9. **Sanitized User Errors**: Technical stack traces must never be exposed to public API clients.
10. **Battery / Model Neutrality**: Error handling architecture must remain completely neutral across cell counts, chemistries, hardware vendors, and model paradigms.

---

## Part 21 — Conceptual Implementation Architecture

The future logging and error handling subsystem will be structured across clear architectural layers:

```text
┌─────────────────────────────────────────────────────────────────────────┐
│                    Application / Interface Boundary                     │
│               (FastAPI Exception Handlers / Middleware)                 │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    Structured Logging & Error Pipeline                  │
│       (Context Binding, Severity Routing, Secret Sanitization)          │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
          ┌──────────────────────────┼──────────────────────────┐
          ▼                          ▼                          ▼
┌──────────────────┐       ┌──────────────────┐       ┌──────────────────┐
│   JSON Output    │       │ In-Memory Metric │       │  Observability   │
│ (stdout / files) │       │   Aggregators    │       │ Stream / Sentry  │
└──────────────────┘       └──────────────────┘       └──────────────────┘
```

---

## Architectural Decisions for Future Review

The following implementation-specific decisions will be evaluated in subsequent development milestones:

1. **Structured Logging Library Selection**: Evaluating standard library `logging` vs. `structlog` vs. `loguru` for high-throughput JSON serialization.
2. **Standardized Error Code Catalog**: Formalizing the complete enumeration of error codes across API and domain layers.
3. **Distributed Tracing Integration**: Evaluating OpenTelemetry (OTel) context injection for distributed multi-node twin deployments.
4. **Metrics Export Protocol**: Selecting between Prometheus pull endpoints vs. StatsD / OpenTelemetry push metrics for telemetry throughput tracking.
