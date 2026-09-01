# TwinVolt — Git & Development Workflow Architecture

[![Status: Active Architecture Document](https://img.shields.io/badge/Architecture-Git%20Workflow-blue.svg)](#)
[![Compliance: Mandatory](https://img.shields.io/badge/Compliance-Mandatory-red.svg)](#)

---

## Document Overview & Purpose

This document establishes the formal **Git development workflow, branching strategy, Conventional Commits standard, pull request lifecycle, code review criteria, release engineering procedures, and research-to-production promotion framework** for the **TwinVolt Universal Battery Digital Twin Platform**.

TwinVolt is a universal, battery-agnostic, hardware-agnostic, and model-agnostic software platform. To support high-velocity collaboration among distributed engineers, researchers, and open-source contributors while maintaining pristine architectural integrity, all contributions must adhere strictly to the version control principles defined herein.

---

## Table of Contents

1. [Part 1 — Repository Principles & Governance](#part-1--repository-principles--governance)
2. [Part 2 — Branching Strategy & Topology](#part-2--branching-strategy--topology)
3. [Part 3 — Protected Branch & Merge Policy](#part-3--protected-branch--merge-policy)
4. [Part 4 — Conventional Commits Specification](#part-4--conventional-commits-specification)
5. [Part 5 — Pull Request Standard & Templates](#part-5--pull-request-standard--templates)
6. [Part 6 — Code Review Policy & Architectural Red Flags](#part-6--code-review-policy--architectural-red-flags)
7. [Part 7 — Pre-Merge Quality Gates](#part-7--pre-merge-quality-gates)
8. [Part 8 — Semantic Versioning & Pre-1.0 Strategy](#part-8--semantic-versioning--pre-10-strategy)
9. [Part 9 — Release Engineering & Lifecycle Procedure](#part-9--release-engineering--lifecycle-procedure)
10. [Part 10 — Changelog Standards](#part-10--changelog-standards)
11. [Part 11 — Breaking Change Handling & Deprecation](#part-11--breaking-change-handling--deprecation)
12. [Part 12 — Dependency Management Workflow](#part-12--dependency-management-workflow)
13. [Part 13 — Documentation & Test Synchronization Rules](#part-13--documentation--test-synchronization-rules)
14. [Part 14 — Security-Sensitive Changes & Secret Policies](#part-14--security-sensitive-changes--secret-policies)
15. [Part 15 — Generated & Large File Policies](#part-15--generated--large-file-policies)
16. [Part 16 — Research-to-Production Promotion Pipeline](#part-16--research-to-production-promotion-pipeline)
17. [Part 17 — Requirements-to-Release Traceability Framework](#part-17--requirements-to-release-traceability-framework)
18. [Part 18 — Rollback, Revert & Hotfix Strategy](#part-18--rollback-revert--hotfix-strategy)
19. [Part 19 — Summary of Core Workflow Principles](#part-19--summary-of-core-workflow-principles)

---

## Part 1 — Repository Principles & Governance

TwinVolt enforces five foundational repository principles:

1. **Linear & Traceable History**: Every change merged into `main` must be traceable to a specific requirement, issue, and code review.
2. **Always-Releasable Main Branch**: The `main` branch represents stable, fully tested, and passing code at all times. Incomplete features reside on feature branches.
3. **Atomic, Focused Commits**: Each commit must represent a single logical change with an explicit Conventional Commit message explaining *why* the change was made.
4. **Architectural Guardrails**: Pull requests that violate layer boundaries, hardcode battery parameters, or couple the core engine to specific hardware prototypes will be rejected during review.
5. **Zero Secrets in Git**: Sensitive credentials, API keys, private certificates, and real `.env` files must **never** enter the Git commit history.

---

## Part 2 — Branching Strategy & Topology

TwinVolt adopts a streamlined, professional Git branching strategy designed for modular engineering:

```text
  main (Protected: Stable, Passing, Releasable)
   │
   ├── feature/canonical-telemetry-schema ──► PR ──► main (Squash / Merge)
   │
   ├── fix/ekf-covariance-singularity ──────► PR ──► main (Squash / Merge)
   │
   ├── docs/architecture-adapter-boundaries ─► PR ──► main (Squash / Merge)
   │
   ├── research/neural-ecm-surrogate ────────► Experiment ──► Validation Report ──► feature/*
   │
   └── release/v0.2.0 ──────────────────────► Tag v0.2.0 ──► main
```

### Branch Categories & Naming Conventions:

| Branch Prefix | Purpose & Scope | Example Branch Name |
| :--- | :--- | :--- |
| **`main`** | The default, protected branch. Contains stable, verified code only. | `main` |
| **`feature/*`** | Developing new platform capabilities, adapters, or estimators. | `feature/ekf-soc-estimator`<br>`feature/mqtt-telemetry-adapter` |
| **`fix/*`** | Correcting functional bugs or non-security errors. | `fix/voltage-lookup-interpolation`<br>`fix/timestamp-jitter-handling` |
| **`docs/*`** | Documentation additions, architecture updates, and ADRs. | `docs/telemetry-schema-spec`<br>`docs/adr-0003-timescaledb` |
| **`research/*`** | Experimental modeling, exploratory algorithms, and solver tests. | `research/pybamm-dfn-fast-solver`<br>`research/kalman-adaptive-noise` |
| **`refactor/*`** | Code quality improvements, typing cleanups, zero functional change. | `refactor/isolate-domain-types`<br>`refactor/adapter-protocol-interfaces` |
| **`release/*`** | Preparing a formal version release, bumping versions, changelogs. | `release/v0.1.0`<br>`release/v0.2.0-rc.1` |
| **`hotfix/*`** | Critical security or production emergency patches against tagged releases. | `hotfix/v0.1.1-secret-redaction` |

---

## Part 3 — Protected Branch & Merge Policy

### 3.1 Protected `main` Branch Rules
- **No Direct Pushes**: Direct `git push origin main` is strictly prohibited for all developers.
- **Mandatory Pull Requests**: All changes must arrive on `main` via a reviewed and approved Pull Request.
- **Quality Gate Clearance**: All automated CI checks (linting, typing, unit tests, integration tests) must pass with 100% success before merging.
- **Mandatory Branch Deletion**: Feature, fix, and release branches must be deleted automatically upon successful merge to prevent repository branch clutter.

### 3.2 Merge Strategy: Squash and Merge vs. Rebase
- **Squash and Merge (Default)**: Used for `feature/*`, `fix/*`, `docs/*`, and `refactor/*` PRs. Compresses intermediate development commits into a single, clean, semantic commit on `main`.
- **Rebase and Merge**: Used for `release/*` branches to preserve milestone release commit structures.
- **No Merge Commits**: Avoid noisy `Merge branch 'foo' into 'main'` merge bubble commits.

---

## Part 4 — Conventional Commits Specification

All commit messages in TwinVolt must strictly follow the [Conventional Commits v1.0.0](https://www.conventionalcommits.org/) specification.

```text
<type>(<optional scope>): <short imperative description>

[optional detailed body explaining WHY the change was made]

[optional footer(s): BREAKING CHANGE: <description>, Fixes #123, Refs ADR-0002]
```

### 4.1 Allowed Commit Types & TwinVolt Examples

| Type | Intended Scope | TwinVolt Example Commit Summary |
| :--- | :--- | :--- |
| **`feat`** | New platform capability or interface | `feat(estimation): add discrete ekf soc estimation algorithm` |
| **`fix`** | Bug fix or calculation correction | `fix(telemetry): reject negative resistance values during parsing` |
| **`docs`** | Documentation or specification update | `docs(testing): document floating-point tolerance standards` |
| **`refactor`**| Restructuring code without functional change | `refactor(domain): decouple battery pack from serialization format` |
| **`test`** | Adding or modifying test suites | `test(models): add pulse discharge step-response regression tests` |
| **`perf`** | Performance or latency optimization | `perf(solver): optimize matrix inversion in 2-rc ecm loop` |
| **`security`**| Security patches or secret redactions | `security(logging): sanitize mqtt connection string credentials` |
| **`build`** | Build system, packaging, or Docker updates | `build(docker): optimize multi-stage python container build` |
| **`ci`** | CI/CD automation workflow changes | `ci(github): add automated mypy and ruff quality gates` |
| **`chore`** | Routine tool or dependency maintenance | `chore(deps): update ruff to version 0.5.0` |
| **`research`**| Exploratory experiments on research branches| `research(soh): evaluate capacity fade curve fitting on nmc data` |

### 4.2 Formatting Rules:
- **Imperative Mood**: Use "add", "fix", "refactor", not "added", "fixing", "refactored".
- **Lowercase Summary**: The summary line must start with a lowercase letter and contain **no trailing period**.
- **Line Length**: Subject line maximum **72 characters**; body lines wrapped at **80 characters**.
- **Breaking Changes**: Indicated with a `!` after type/scope (e.g., `feat(api)!: redesign telemetry websocket message format`) or via a `BREAKING CHANGE:` footer.

---

## Part 5 — Pull Request Standard & Templates

Every Pull Request is a formal proposal to modify the shared platform baseline.

### 5.1 Pull Request Scope Guidelines
- **Small & Cohesive**: PRs should ideally be $< 400$ lines of diff (excluding generated reference datasets or lockfiles).
- **Single Responsibility**: Do not combine an estimation feature, an unrelated adapter bug fix, and a typo correction into a single PR.

### 5.2 Mandatory PR Description Template
```markdown
## 1. Description & Context
<!-- Provide a concise summary of the change and the engineering problem it solves. -->

## 2. Type of Change
- [ ] `feat`: New feature or capability
- [ ] `fix`: Bug fix
- [ ] `docs`: Documentation addition or update
- [ ] `refactor`: Code restructuring without behavioral change
- [ ] `test`: New or updated tests
- [ ] `perf`: Performance improvement
- [ ] `chore`: Tooling, dependency, or repository maintenance
- [ ] `research`: Experimental research findings

## 3. Architectural Impact & Compliance
- [ ] **Universal Architecture**: Preserves battery, chemistry, cell-count, and hardware neutrality.
- [ ] **Layer Isolation**: Domain logic does not import infrastructure, databases, or drivers.
- [ ] **Model Agnosticism**: Does not hardcode dependence on PyBaMM or a specific solver.

## 4. Verification & Testing Performed
<!-- Detail the automated and manual verification executed. -->
- Command executed: `pytest tests/unit/ -v`
- Static typing check: `mypy --strict`
- Linting check: `ruff check .`

## 5. Security & Configuration Check
- [ ] Zero secrets, passwords, or private keys in code, tests, or documentation.
- [ ] Configuration defaults documented in `.env.example` (if applicable).

## 6. Related Issues & ADRs
- Closes # [Issue Number]
- Relates to ADR- [ADR Number]
```

---

## Part 6 — Code Review Policy & Architectural Red Flags

Code review is TwinVolt’s primary line of defense for maintaining scientific accuracy and architectural purity.

### 6.1 Review Checklist Focus Areas:
1. **Physical & Mathematical Correctness**: Are equations valid, units explicit, and floating-point tolerances applied?
2. **Layer Boundary Compliance**: Does the change respect the Golden Boundary Rule (Domain has zero infrastructure dependencies)?
3. **Type Safety**: Are type annotations explicit with zero unvetted `Any` types or untyped dictionaries?
4. **Test Rigor**: Are unit tests deterministic with fixed random seeds?
5. **Observability**: Are errors structured and free from credential leaks?

### 6.2 Architectural Red Flags (Instant Rejection Criteria):
```text
🚩 Hardcoding a fixed cell count (e.g., assuming 2S, 3S, or 4S in core domain logic).
🚩 Hardcoding battery chemistry (e.g., if chemistry == "LFP" in twin core).
🚩 Importing infrastructure libraries (FastAPI, PostgreSQL, MQTT, Serial) into `src/domain/`.
🚩 Hardcoding PyBaMM as a mandatory core engine requirement.
🚩 Committing a `.env` file, secret key, password, or private certificate.
🚩 Merging code with failing tests, `mypy` type errors, or `ruff` lint warnings.
🚩 Introducing undocumented breaking changes to Canonical Telemetry schemas.
```

---

## Part 7 — Pre-Merge Quality Gates

Before any branch can be merged into `main`, it must clear six automated quality gates:

```text
┌─────────────────────────────────────────────────────────────────────────┐
│                     TwinVolt Pre-Merge Quality Gates                    │
├───────────────────┬─────────────────────────────────────────────────────┤
│ 1. Code Style     │ `ruff format --check .` (0 formatting differences)  │
├───────────────────┼─────────────────────────────────────────────────────┤
│ 2. Linting        │ `ruff check .` (0 errors, 0 warnings)               │
├───────────────────┼─────────────────────────────────────────────────────┤
│ 3. Type Checking  │ `mypy --strict src/ tests/` (0 type errors)         │
├───────────────────┼─────────────────────────────────────────────────────┤
│ 4. Test Suites    │ `pytest tests/unit/ tests/integration/` (100% pass) │
├───────────────────┼─────────────────────────────────────────────────────┤
│ 5. Security Scan  │ 0 secrets detected; 0 high-severity CVEs in deps    │
├───────────────────┼─────────────────────────────────────────────────────┤
│ 6. Documentation  │ Documentation updated if contracts/schemas changed  │
└───────────────────┴─────────────────────────────────────────────────────┘
```

---

## Part 8 — Semantic Versioning & Pre-1.0 Strategy

TwinVolt follows the **Semantic Versioning 2.0.0** (`MAJOR.MINOR.PATCH`) standard.

```text
┌─────────────────────────────────────────────────────────────────────────┐
│                              vMAJOR.MINOR.PATCH                         │
├───────────────┬─────────────────────────────────────────────────────────┤
│ **MAJOR**     │ Incompatible API, canonical schema, or architectural    │
│               │ breaking changes.                                       │
├───────────────┼─────────────────────────────────────────────────────────┤
│ **MINOR**     │ Backward-compatible new capabilities, estimators, or    │
│               │ protocol adapters.                                      │
├───────────────┼─────────────────────────────────────────────────────────┤
│ **PATCH**     │ Backward-compatible bug fixes, performance tuning, or   │
│               │ documentation corrections.                              │
└───────────────┴─────────────────────────────────────────────────────────┘
```

### 8.1 Pre-1.0 Development Lifecycle (`v0.y.z`)
- While in active foundation development (Level 0 through Level 1):
  - `0.y.z`: The platform is evolving rapidly.
  - Incrementing `y` (e.g., `0.1.0` $\rightarrow$ `0.2.0`) indicates significant new architectural milestones or breaking foundation changes.
  - Incrementing `z` (e.g., `0.1.0` $\rightarrow$ `0.1.1`) indicates backward-compatible enhancements and bug fixes.
- **Pre-Release Identifiers**:
  - Alpha releases: `v0.1.0-alpha.1` (Internal foundation milestone).
  - Beta releases: `v0.1.0-beta.1` (Feature complete for testing).
  - Release Candidates: `v0.1.0-rc.1` (Staged for final validation).

---

## Part 9 — Release Engineering & Lifecycle Procedure

Releases are managed through a structured 8-step lifecycle:

```text
Development (feature/*) ──► Merge to main ──► Create release/vX.Y.Z ──► Verification Suite
                                                                             │
Release Published ◄── Create GitHub Release ◄── Git Tag vX.Y.Z ◄── Update CHANGELOG.md
```

1. **Milestone Completion**: All issues and PRs planned for the target milestone are merged into `main`.
2. **Create Release Branch**: Branch off `main` to `release/vX.Y.Z`.
3. **Full Verification Suite**: Run the complete test suite including long-running simulation drive-cycle benchmarks.
4. **Version Bump & Documentation Sync**: Update version strings in `pyproject.toml` and documentation indexes.
5. **Changelog Generation**: Compile `CHANGELOG.md` entry documenting all additions, fixes, and changes.
6. **PR & Merge to Main**: Merge `release/vX.Y.Z` into `main` via a dedicated release PR.
7. **Git Tagging**: Create an annotated, signed Git tag:
   ```bash
   git tag -a v0.1.0 -m "Release v0.1.0 — Engineering Foundation Milestone"
   ```
8. **GitHub Release Publication**: Publish the release notes and container artifacts.

---

## Part 10 — Changelog Standards

The project maintains a root `CHANGELOG.md` adhering strictly to the [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) standard.

### Standard Changelog Section Headers:
- **`Added`**: New features, adapters, models, or documentation.
- **`Changed`**: Changes in existing functionality or architectural interfaces.
- **`Deprecated`**: Features slated for removal in upcoming releases.
- **`Removed`**: Features or configurations removed in this release.
- **`Fixed`**: Bug fixes and calculation corrections.
- **`Security`**: Vulnerability patches and secret protection enhancements.

---

## Part 11 — Breaking Change Handling & Deprecation

To maintain stability across user integrations:
1. **Advance Notice**: Any planned breaking change to a public API, canonical telemetry schema, or battery profile format must be documented with a `@deprecated` annotation at least one minor release cycle prior to removal.
2. **Migration Guide**: Every breaking change must be accompanied by a step-by-step migration guide in `docs/` and a dedicated section in `CHANGELOG.md`.

---

## Part 12 — Dependency Management Workflow

Third-party dependencies introduce security surface area and maintenance overhead:
1. **Justification Required**: Introducing any new third-party library requires an explicit rationale in the PR description.
2. **License Compatibility**: Dependencies must possess permissive open-source licenses (MIT, Apache 2.0, BSD-3-Clause). Copyleft licenses (GPL/AGPL) require formal architectural approval.
3. **Strict Separation**: Keep runtime dependencies (`[project.dependencies]`) separated from development/test dependencies (`[project.optional-dependencies] dev = [...]`).

---

## Part 13 — Documentation & Test Synchronization Rules

- **Zero Untested Features**: No feature PR will be approved without accompanying unit or simulation regression tests.
- **Documentation in Lock-Step**: When a public interface, configuration parameter, or architectural boundary is modified, the corresponding documentation must be updated within the exact same PR.

---

## Part 14 — Security-Sensitive Changes & Secret Policies

### 14.1 Zero Secrets Policy
- Passwords, API tokens, MQTT credentials, and private keys must **never** be committed to Git.
- Real `.env` files are strictly excluded via [.gitignore](file:///.gitignore).

### 14.2 Emergency Secret Exposure Response:
If a secret or credential is inadvertently committed to Git:
1. **Immediate Revocation**: Consider the credential compromised immediately. Rotate and revoke the secret at the provider level within 15 minutes.
2. **History Purge**: Do not simply delete the file in a new commit. Use `git-filter-repo` or BFG Repo-Cleaner to rewrite history and purge the secret from all branches and tags.
3. **Post-Mortem**: Document the exposure incident and update pre-commit secret scanning rules.

---

## Part 15 — Generated & Large File Policies

### 15.1 Prohibited Generated Files
The following generated artifacts must never be tracked in Git:
- Python bytecode (`__pycache__/`, `*.pyc`).
- Virtual environments (`.venv/`, `venv/`).
- Test & lint caches (`.pytest_cache/`, `.ruff_cache/`, `.mypy_cache/`, `htmlcov/`).
- Local logs (`*.log`, `logs/`) and SQLite temporary databases (`*.sqlite`, `*.db`).
- Node build outputs (`node_modules/`, `.vite/`, `dist/`).

### 15.2 Large Files & Reference Datasets ($> 5\text{ MB}$)
- Large battery cycler datasets (raw CSV/HDF5/Parquet files) must not be checked directly into Git.
- Use synthetic generator scripts (`scripts/generate_synthetic_telemetry.py`) or external artifact storage with versioned checksum manifests.

---

## Part 16 — Research-to-Production Promotion Pipeline

A critical discipline in scientific software engineering is separating exploratory research from production runtime code.

```text
┌─────────────────────────────────────────────────────────────────────────┐
│ 1. Exploratory Research (`research/*` branch)                           │
│    • Prototype experimental estimators, ML surrogates, PyBaMM solvers.  │
│    • Jupyter notebooks and scratch scripts allowed in research branch.  │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │ (Empirical Validation)
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 2. Research Validation Report & Architecture Review                     │
│    • Author technical report (`docs/specifications/`) & benchmark stats.│
│    • Propose formal Architecture Decision Record (ADR).                 │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │ (ADR Accepted)
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 3. Production Implementation (`feature/*` branch)                       │
│    • Clean, pure Python implementation conforming to Domain interfaces. │
│    • Strict type hints (`mypy --strict`), Ruff linting, Google docstrings│
└────────────────────────────────────┬────────────────────────────────────┘
                                     │ (Quality Gates Pass)
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 4. Mainline Promotion (`main` branch)                                   │
│    • Merged into core platform baseline with 100% test coverage.        │
└─────────────────────────────────────────────────────────────────────────┘
```

> [!CRITICAL]
> **Experimental research notebooks and exploratory scripts must NEVER be merged directly into `main` without completing the formal 4-stage promotion pipeline.**

---

## Part 17 — Requirements-to-Release Traceability Framework

TwinVolt maintains a bi-directional traceability graph connecting business requirements to released code:

```text
Requirement (Issue #101)
     │
     ▼
Architecture Decision (ADR-0004)
     │
     ▼
Feature Branch (`feature/ukf-soc-estimator`)
     │
     ▼
Conventional Commit (`feat(estimation): implement unscented kalman filter`)
     │
     ▼
Pull Request (PR #142) ──► Verified by `tests/simulation/test_ukf.py`
     │
     ▼
Merged to `main` ──► Released in Git Tag `v0.2.0`
```

---

## Part 18 — Rollback, Revert & Hotfix Strategy

When a bug or regression is detected on `main` or in a release:

```text
┌──────────────────────────────┬──────────────────────────────────────────────────────────┐
│ Regression Scenario          │ Remediation Strategy                                     │
├──────────────────────────────┼──────────────────────────────────────────────────────────┤
│ Defect on `main` branch      │ Execute clean `git revert <commit_sha>` via PR.          │
│                              │ Never rewrite history (`git reset --hard`) on `main`.    │
├──────────────────────────────┼──────────────────────────────────────────────────────────┤
│ Critical Release Defect      │ Branch `hotfix/vX.Y.Z+1` from release tag.               │
│                              │ Apply targeted fix -> Tag `vX.Y.Z+1` -> Merge to `main`. │
├──────────────────────────────┼──────────────────────────────────────────────────────────┤
│ Database Schema Regression   │ Apply downward database migration script.                │
├──────────────────────────────┼──────────────────────────────────────────────────────────┤
│ Corrupted Model Config       │ Roll back battery profile YAML to previous Git revision. │
└──────────────────────────────┴──────────────────────────────────────────────────────────┘
```

---

## Part 19 — Summary of Core Workflow Principles

The **10 Cardinal Rules of TwinVolt Git & Development**:

1. **`main` is Always Releasable**: Never merge broken or untested code into `main`.
2. **Branch from `main`, Merge via PR**: All work happens on short-lived branches merged through reviewed pull requests.
3. **Conventional Commits Mandatory**: Commit messages must follow the `<type>(<scope>): <summary>` specification.
4. **Architectural Guardrails First**: Never compromise universal battery neutrality for quick convenience.
5. **No Secrets Anywhere**: Zero credentials, tokens, or private keys in Git history.
6. **Lock-Step Documentation**: Code, schemas, tests, and documentation must be updated in the same PR.
7. **Pre-Merge Quality Gates**: 100% test pass, `mypy --strict`, and `ruff` compliance required before merging.
8. **Research is Not Production**: Experimental notebooks must follow the formal promotion pipeline before reaching `main`.
9. **Semantic Versioning Integrity**: Increment version numbers strictly according to SemVer 2.0.0.
10. **Revert Over Reset**: Use non-destructive `git revert` to remediate regressions on shared branches.
