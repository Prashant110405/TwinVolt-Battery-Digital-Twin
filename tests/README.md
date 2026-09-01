# TwinVolt — Test Suites (`tests/`)

This directory will contain the comprehensive automated testing suites for the **TwinVolt Universal Battery Digital Twin Platform**.

---

## Testing Strategy & Philosophy

Safety-critical electrochemical software requires rigorous verification at every abstraction layer. TwinVolt adopts a multi-tiered testing strategy to ensure mathematical correctness, data integrity, and system resilience.

---

## Planned Test Structure

As the platform evolves, tests will be organized into the following categories:

```text
tests/
│
├── unit/                   # Fast, isolated unit tests for pure logic & algorithms
│   ├── adapters/           # Protocol parser and decoder unit tests
│   ├── telemetry/          # Schema validation and normalization tests
│   ├── domain/             # Domain entity and configuration validation tests
│   ├── models/             # Mathematical verification of ECM and physics models
│   ├── core/               # State sync and simulation loop unit tests
│   └── estimation/         # Estimator convergence & filter accuracy tests (EKF/UKF)
│
├── integration/            # Cross-module interaction tests
│   ├── ingestion/          # End-to-end telemetry ingestion pipeline tests
│   ├── persistence/        # Database storage, retrieval, and caching tests
│   └── api/                # REST & WebSocket API endpoint tests
│
├── simulation/             # High-fidelity synthetic & drive-cycle simulation tests
│   ├── profiles/           # Standard drive cycles (WLTP, US06, UDDS, synthetic steps)
│   ├── thermal/            # Multi-temperature dynamics & stress tests
│   └── degradation/        # Multi-cycle SOH fade tracking tests
│
├── system/                 # End-to-end full system workflow tests
│   └── e2e_twin_flow/      # Telemetry ingestion -> Twin estimation -> API verification
│
├── hil/                    # Hardware-in-the-Loop & physical hardware integration tests
│   └── test_adapters/      # Mock hardware / real serial & CAN adapter validation
│
└── conftest.py             # Shared pytest fixtures, synthetic telemetry generators & mocks
```

---

## Test Categories Explained

1. **Unit Tests (`unit/`)**
   - Verify isolated functions, classes, and numerical routines without external I/O or network calls.
   - Examples: OCV-SOC curve interpolation, Coulomb counter numerical integration, canonical schema parsing.

2. **Integration Tests (`integration/`)**
   - Verify proper communication between adjacent architectural layers (e.g., Adapters to Canonical Telemetry, State Estimator to Database).

3. **Simulation Tests (`simulation/`)**
   - Run the Digital Twin against known battery benchmark datasets and standard drive cycles (e.g., WLTP, US06, CCCV charge cycles) to verify mathematical fidelity against ground truth.

4. **System & E2E Tests (`system/`)**
   - Validate full data pipelines from ingestion to state estimation output and API response.

5. **Hardware-in-the-Loop (HIL) Tests (`hil/`)**
   - Validate communication and behavior with physical battery management hardware and embedded serial/CAN interfaces using controlled testbenches.

---

## Testing Standards & Conventions

- **Test Runner**: [pytest](https://docs.pytest.org/) will be the primary test framework.
- **Mocking**: External services (MQTT brokers, databases, hardware serial ports) will be mocked in unit and simulation tests using `pytest-mock` or custom synthetic fixtures.
- **Deterministic Runs**: All mathematical and simulation tests must use fixed random seeds to guarantee repeatable, deterministic outcomes.
- **Coverage**: High test coverage across core mathematical engines and state estimation pipelines.
