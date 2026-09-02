# TwinVolt — Documentation (`docs/`)

This directory serves as the central knowledge base for the **TwinVolt Universal Battery Digital Twin Platform**.

---

## Purpose & Scope

As TwinVolt progresses through its development lifecycle, all formal architectural specifications, technical designs, schema definitions, and engineering guides will be maintained here.

## Core Engineering Documents

- [Engineering Standards & Development Conventions](engineering-standards.md) — Mandatory coding, typing, architectural, testing, and review standards for all TwinVolt development.
- [Configuration Management Architecture](configuration.md) — Specifications, schema strategies, boundary isolation rules, and secrets management for the platform.
- [Error Handling & Logging Architecture](error-handling-and-logging.md) — Exception propagation, fail-safe rules, structured logging specifications, and telemetry stream constraints.
- [Testing Strategy & Verification Architecture](testing-strategy.md) — Test pyramid, numerical validation tolerances, physical plausibility checks, HIL, and quality gates.
- [Documentation Architecture & Standards](documentation-standards.md) — Knowledge organization, document hierarchy, ADR processes, traceability framework, and technical precision standards.
- [Git & Development Workflow Architecture](git-workflow.md) — Branching strategy, Conventional Commits, PR standards, pre-merge quality gates, and release lifecycles.
- [Foundation Validation & Architecture Gate Report](foundation-validation.md) — Formal Level 0 architecture gate review, universality audit, layering verification, and readiness assessment.

## Domain, Telemetry & Configuration Specifications

- [Universal Battery Domain Entities](domain/battery-entities.md) — Structural hierarchy, entities (Cell, Module, Pack, System), value objects, and physical invariants for generic battery representations.
- [Canonical Telemetry Model](telemetry/canonical-model.md) — Universal internal contracts, snapshot models, discrete sensor addressing, SI unit standards, and deterministic serialization.
- [Battery Profile & Configuration Schemas](schemas/battery-profile-schemas.md) — Declarative YAML/JSON schemas, safe profile loaders, validation contracts, and domain materialization pipelines.
- [Level 1 Domain & Data Foundation Gate Report](domain-validation.md) — Formal Level 1 architecture gate review, universality test matrix, cross-model consistency audit, and sign-off.
- [Level 2 Architecture Decomposition & Plan](architecture/level-2-decomposition.md) — Pluggable model architecture, state estimation contracts, electro-thermal models, and subtask breakdown.
- [Mathematical Core & Model Contracts Specification](specifications/mathematical-core.md) — State space vectors ($x[k], u[k], y[k]$), `BatteryModel` protocol, numerical ODE integrators, and physical invariant contracts.
- [Electro-Thermal Model Specification](specifications/electro-thermal-model.md) — N-RC Equivalent Circuit Models (0-RC, 1-RC Thevenin, 2-RC Dual Polarization), 0D lumped thermal dynamics, and loss coupling.
- [Physics-Based Model Backend & PyBaMM Adapter Specification](specifications/physics-model-adapter.md) — SPM, SPMe, DFN electrochemical model integration, parameter translation layer, and surrogate fallback.
- [Time-Series Persistence & Storage Specification](specifications/storage-repository.md) — Protocols, query semantics, bounded circular buffers, and file append persistence.
- [Internal Event Bus & Observability Specification](specifications/event-bus-and-observability.md) — In-process publish-subscribe broker, priority ordering, fault isolation, and execution metrics.
- [Level 2 Battery Modeling & Estimation Gate Report](models-validation.md) — Formal Level 2 architecture gate review, universality test matrix, invariant audit, and sign-off.

---

## Planned Documentation Structure

The following documentation categories are planned for this directory:

1. **Architecture & System Design (`docs/architecture/`)**
   - High-level system topology and layer boundaries.
   - Component relationship diagrams and data flow specifications.
   - Subsystem interaction contracts (Adapters, Core, Estimators, Storage).

2. **Architecture Decision Records (`docs/adr/`)**
   - Formal ADRs documenting significant technical, architectural, and design choices.
   - Trade-off analyses (e.g., choice of state estimation algorithms, database selections, protocol adapters).

3. **Technical Specifications & Models (`docs/specifications/`)**
   - Electro-thermal battery model specifications (ECM 1-RC/2-RC, PyBaMM physics integration).
   - State estimation mathematical definitions (Coulomb Counting, EKF/UKF SOC, SOH capacity fade).
   - Thermal dynamics and cooling model specifications.

4. **Data Schemas & Contracts (`docs/schemas/`)**
   - Canonical telemetry payload definitions (JSON Schema, Pydantic specs).
   - Battery pack definition schemas (cell counts, chemistries, thermal limits).
   - API contract definitions (OpenAPI / Swagger specs).

5. **API & Interface Documentation (`docs/api/`)**
   - REST API endpoint documentation.
   - WebSocket / streaming telemetry subscription protocols.
   - Adapter plugin interfaces.

6. **Development & Contribution Guides (`docs/guides/`)**
   - Local development environment setup instructions.
   - Code formatting, linting, and type-checking standards.
   - Contribution workflows and PR review criteria.

7. **Testing & Validation Guides (`docs/testing/`)**
   - Unit and integration testing protocols.
   - Synthetic data generation and drive-cycle simulation procedures.
   - Hardware-in-the-Loop (HIL) setup and validation instructions.

---

## Guidelines for Documentation

- All documentation must be written in GitHub Flavored Markdown (`.md`).
- Diagrams should use Mermaid syntax where possible for version-controlled visual clarity.
- Keep documentation synchronized with active codebase changes as milestones progress.
