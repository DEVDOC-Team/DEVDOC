# DEVDOC

**DEVDOC** is a web application for investigating operational incidents and preparing safe, reviewable remediation proposals. Its React frontend provides an operator workspace for projects, incidents, investigations, approvals, and audit history. The FastAPI backend provides authenticated APIs, persistence, and an investigation orchestrator that gathers evidence and can optionally use external reasoning and search providers.

> **Project status:** The React frontend is implemented. The backend status matrix records phases 1-26 as complete or implemented within the stated scope. The verification report records 482 passed, 14 skipped, and 0 failed tests on October 25, 2026; see that report for its scope and environment. LLM reasoning, knowledge search, sandbox verification, and artifact recording are opt-in integrations. Human approval records a decision only; automated production changes and incident resolution are not implemented. Phase 19 covers specific database write-boundary hardening and is not a security certification. Production rate limiting requires shared Redis and trusted deployment configuration.

---

# 1. Overview

## What is DEVDOC?

DEVDOC supports an operator-led incident investigation and review workflow:

```
Detect
  ↓
Investigate
  ↓
Gather Evidence
  ↓
Reason
  ↓
Diagnose
  ↓
Generate Fix
  ↓
Verify in Sandbox
  ↓
Human Approval
  ↓
Record Decision
```

- **Implemented (Phases 1-16.1)**: Backend foundation, Supabase models and RLS, JWT authentication, project and incident APIs, chat history, GitHub inspection, orchestration, evidence processing, optional reasoning/search, RCA, and non-executing fix proposals.
- **Implemented (Phase 17, opt-in)**: Isolated sandbox verification using explicitly injected trusted commands and a source workspace.
- **Implemented (Phase 18)**: Human-only review and audit of eligible proposals. Approval does not apply patches or perform production changes.

## Why DEVDOC?

- **Fragmented Operational Context**: Logs, metrics, stack traces, and GitHub commit history are scattered across disparate tools, slowing down triage during critical outages.
- **Cognitive Overload Under Fire**: Engineers manually piece together timeline events under severe time pressure, leading to diagnostic errors and extended downtime.
- **Context Blindness**: Traditional observability dashboards display alerts but lack direct awareness of repository code, recent pull requests, or CI/CD workflow failures.
- **Unsafe Automation**: Blind automated remediation risks catastrophic secondary outages without isolated sandbox verification and explicit human approval.

---

# 2. Architecture

The DEVDOC platform separates the frontend, API handling, authorization, database persistence, and investigation orchestration:

```
               User / Web Frontend
                       │
                       ▼
               FastAPI REST API
                       │
       ┌───────────────┴───────────────┐
       ▼                               ▼
Authentication & JWT            Authoritative Project
  (Supabase Auth)                 & Incident Guard
       │                               │
       └───────────────┬───────────────┘
                       ▼
            Investigation REST API
                       │
                       ▼
         PostgreSQL + Row Level Security (RLS)
                       │
   ════════════════════╪═══════════════════════════════════════════
                       │ [Phase 10+ Integration Boundary]
                       ▼
              DEVDOC Orchestrator          [Phase 10 — Implemented]
                       │
       ┌───────────────┼───────────────┐
       ▼               ▼               ▼
  GitHub Agent   Docker Agent   Monitoring Agent [Phase 11 — Implemented]
       │               │               │
       └───────────────┬───────────────┘
                       ▼
                Evidence Engine            [Phase 12 — Implemented]
                       │
                       ▼
            Tavily Knowledge Search        [Phase 14 — Implemented, opt-in]
                       │
                       ▼
         NVIDIA Nemotron via Nebius        [Phase 13 — Implemented, opt-in]
                       │
                       ▼
               Root Cause Engine           [Phase 15 — Implemented, opt-in]
                       │
                       ▼
            Fix Proposal Generator          [Phase 16 — Implemented, opt-in]
                       │
                       ▼
             Sandbox Verification          [Phase 17 — Implemented, opt-in]
                       │
                       ▼
             Human Approval Gate           [Phase 18 — Implemented]
                       │
                       ▼
             Production Resolution         [Not Implemented]
```

---

# 3. Technology Stack

### Current full-stack implementation

| Layer                       | Technology                                    | Purpose                                                |
| --------------------------- | --------------------------------------------- | ------------------------------------------------------ |
| Frontend                    | React 19, TypeScript 6, Vite 8                | Browser application and build tooling                  |
| Frontend assets             | Lucide React, CSS, Source Sans 3              | Icons, styling, and locally bundled typography         |
| Backend runtime             | Python 3.13, FastAPI, Uvicorn                 | Asynchronous REST API                                  |
| Request/Response Validation | Pydantic v2                                   | Strict schema validation with `extra="forbid"`         |
| Settings & Config           | pydantic-settings                             | Type-safe environment variable management              |
| ORM & Queries               | SQLAlchemy 2.0 (Async)                        | Asynchronous PostgreSQL persistence layer              |
| Database & Auth             | PostgreSQL 16 / Supabase                      | Relational store with Row Level Security (RLS)         |
| Database Migrations         | Alembic                                       | Version-controlled database schema migrations          |
| Local/test database         | SQLite, aiosqlite                             | Lightweight fallback and isolated tests                |
| Integrations                | HTTPX, GitHub API; optional Nebius and Tavily | Repository inspection, reasoning, and knowledge search |
| Rate limiting               | Redis when configured                         | Shared limits across production workers                |
| Testing                     | pytest, pytest-asyncio, HTTPX, Vitest         | Backend and frontend test suites                       |
| Code quality                | Ruff, Oxlint                                  | Backend and frontend linting                           |
| Container and CI            | Docker, GitHub Actions                        | Backend image and automated CI workflow                |

### Optional integrations and guarded workflow stages

| Component                | Current implementation                                       | Phase    |
| ------------------------ | ------------------------------------------------------------ | -------- |
| Root-cause reasoning     | Evidence-grounded analysis; external LLM reasoning is opt-in | Phase 15 |
| Fix generation           | Validated remediation proposals; no automatic execution      | Phase 16 |
| Sandbox verification     | Isolated Docker provider; opt-in with trusted inputs         | Phase 17 |
| Human approval and audit | Verification-bound human decision; no production execution   | Phase 18 |

---

# 4. Project Status / Roadmap

The repository documents 26 backend phases alongside the implemented React frontend. Production deployment still requires environment-specific configuration and validation.

| Phase |         Status          | Title                           | Description                                                                                                                 |
| :---: | :---------------------: | ------------------------------- | --------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------ |
|   1   |       ✅ Complete       | Backend Foundation              | FastAPI application structure, configuration, health endpoints, logging                                                     |
|   2   |       ✅ Complete       | Supabase Database Foundation    | PostgreSQL connection pooling, async engine, base schema                                                                    |
|   3   |       ✅ Complete       | Database Models & Relationships | Full relational schema for Users, Projects, Repositories, Incidents, Investigations                                         |
|   4   |       ✅ Complete       | Supabase Row Level Security     | PostgreSQL RLS policies, `has_project_access` security functions                                                            |
|   5   |       ✅ Complete       | Authentication & Authorization  | Supabase JWT verification, session claim propagation, profile sync                                                          |
|   6   |       ✅ Complete       | User & Project REST APIs        | User profile endpoints, project CRUD, anti-spoofing ownership boundaries                                                    |
|   7   |       ✅ Complete       | GitHub Integration              | GitHub OAuth, signed CSRF state, repository attachment, code/commit/PR inspection                                           |
|   8   |       ✅ Complete       | Incident Management             | Operational incident model, controlled 5-state lifecycle, bounded pagination                                                |
|   9   |       ✅ Complete       | Investigation API               | Investigation data contract, finite state machine, dual boundary validation                                                 |
|  10   |       ✅ Complete       | DEVDOC Orchestrator             | Autonomous agent orchestrator package, workflow coordination                                                                |
|  11   |       ✅ Complete       | Investigation Agents            | Specialized GitHub, Docker, and Monitoring inspection agents                                                                |
|  12   |       ✅ Complete       | Evidence Engine                 | Bounded evidence normalization, validation, deduplication, timeline assembly, and graph correlation                         |
|  13   |       ✅ Complete       | NVIDIA Nemotron + Nebius        | Provider abstraction, structured evidence reasoning, budget guardrails, token/cost tracking                                 |
|  14   |       ✅ Complete       | Knowledge Search / Tavily       | Bounded, opt-in external knowledge retrieval with provenance                                                                |
|  15   |       ✅ Complete       | Root Cause Engine               | Evidence-referenced hypotheses, contradictions, confidence, and cautious cause selection                                    |
|  16   |       ✅ Complete       | Fix Generator                   | Evidence-grounded remediation proposals with patch, secret, path, risk, rollback, and verification validation; no execution |
| 16.1  |       ✅ Complete       | Chat History                    | Persisted, paginated, incident-scoped conversations and user/assistant messages, optionally linked to an investigation      |
|  17   | ✅ Implemented (opt-in) | Sandbox Verification            | Isolated, bounded verification of Phase 16 proposals; injected trusted commands only; no production access                  |
|  18   |       ✅ Complete       | Human Approval & Audit          | Human-only decisions bound to passing Phase 17 verification; immutable audit; no production execution                       |
|  19   |       ✅ Complete       | Targeted implementation         | Security Hardening                                                                                                          | Approval/audit database write-boundary hardening; not a full security certification        |
|  20   |       ✅ Complete       | Implemented                     | API Rate Limiting                                                                                                           | Tenant-based quotas and IP burst protection; production requires shared Redis              |
|  21   |       ✅ Complete       | Implemented                     | Observability                                                                                                               | Prometheus metrics; OpenTelemetry collector is optional                                    |
|  22   |       ✅ Complete       | Implemented                     | Load Testing                                                                                                                | Locust and concurrency scenarios; benchmark is not a production capacity guarantee         |
|  23   |       ✅ Complete       | Implemented                     | Docker & CI/CD                                                                                                              | Non-root backend Docker image and GitHub Actions CI workflow                               |
|  24   |       ✅ Complete       | Implemented in documented scope | Production Architecture                                                                                                     | Primary/read-replica routing and resilience design; multi-region cloud deployment deferred |
|  25   |       ✅ Complete       | Complete                        | Backend Evaluation                                                                                                          | Regression verification recorded in the backend report                                     |
|  26   |       ✅ Complete       | Complete                        | Documentation                                                                                                               | Project, backend, frontend, and security guides                                            |

---

# 5. Repository Structure

```
devdoc/
├── backend/
│   ├── .dockerignore
│   ├── .env.example              # Template environment configuration
│   ├── Dockerfile                # Production container definition
│   ├── alembic.ini               # Alembic migration configuration
│   ├── pyproject.toml            # Project tool configs (ruff, pytest)
│   ├── requirements.txt          # Production dependencies
│   ├── requirements-dev.txt      # Development & testing dependencies
│   ├── app/
│   │   ├── main.py               # FastAPI entry point & exception handlers
│   │   ├── dependencies.py       # Auth & project authorization dependencies
│   │   ├── api/
│   │   │   ├── router.py         # Main API router aggregator
│   │   │   └── v1/
│   │   │       ├── auth.py       # Profile synchronization (/api/v1/auth)
│   │   │       ├── github.py     # GitHub OAuth & inspection (/api/v1/github)
│   │   │       ├── health.py     # Liveness probe (/api/v1/health)
│   │   │       ├── incidents.py  # Incident management (/api/v1/projects/.../incidents)
│   │   │       ├── investigations.py # Investigation API (/api/v1/.../investigations)
│   │   │       ├── projects.py   # Project management (/api/v1/projects)
│   │   │       ├── ready.py      # Readiness probe (/api/v1/ready)
│   │   │       ├── router.py     # V1 router registration
│   │   │       └── users.py      # User profile management (/api/v1/users)
│   │   ├── core/
│   │   │   ├── config.py         # Type-safe pydantic-settings configuration
│   │   │   ├── exceptions.py     # Standardized JSON error response handlers
│   │   │   ├── logging.py        # Structured audit logger
│   │   │   └── security.py       # JWT verification & cryptographic helpers
│   │   ├── db/
│   │   │   ├── base.py           # SQLAlchemy declarative Base & timestamp mixins
│   │   │   ├── session.py        # Async engine & sessionmaker factories
│   │   │   └── migrations/
│   │   │       ├── env.py        # Alembic runtime environment
│   │   │       └── versions/     # Versioned migration scripts (0001-0008)
│   │   ├── models/               # SQLAlchemy ORM models
│   │   │   ├── chat.py           # Phase 16.1 conversations and messages
│   │   │   ├── approval.py
│   │   │   ├── audit_log.py
│   │   │   ├── deployment.py
│   │   │   ├── evidence.py
│   │   │   ├── fix_proposal.py
│   │   │   ├── github_connection.py
│   │   │   ├── incident.py
│   │   │   ├── investigation.py
│   │   │   ├── project.py
│   │   │   ├── repository.py
│   │   │   └── user.py
│   │   ├── schemas/              # Pydantic request & response schemas
│   │   │   ├── chat.py           # Chat history request/response contracts
│   │   │   ├── auth.py
│   │   │   ├── github.py
│   │   │   ├── health.py
│   │   │   ├── incident.py
│   │   │   ├── investigation.py
│   │   │   ├── project.py
│   │   │   ├── ready.py
│   │   │   └── user.py
│   │   └── services/             # Business logic layer
│   │       ├── chat.py           # Project/incident-scoped chat persistence
│   │       ├── auth.py
│   │       ├── github.py
│   │       ├── incident.py
│   │       ├── investigation.py
│   │       ├── project.py
│   │       └── user.py
│   ├── orchestrator/
│   │   ├── evidence/             # Phase 12 evidence engine and contracts
│   │   ├── fixes/                # Phase 16 safe remediation proposal service
│   │   ├── llm/                  # Phase 13 provider, service, cache, and budget guard
│   │   ├── sandbox/              # Phase 17 providers, isolation, patching, and verification
│   │   └── tests/                # Deterministic orchestrator and LLM tests
│   └── tests/                    # Backend API and database test suite
├── frontend/                     # React/Vite operator web application
├── .github/workflows/            # Backend CI workflow
├── docs/                         # Product and demo documentation
├── BACKEND_VERIFICATION_REPORT.md
├── SECURITY.md                   # Security scope and deployment assumptions
└── README.md                     # Project-wide overview and architecture
```

---

See the [frontend guide](frontend/README.md) and [backend guide](backend/README.md) for package structure, setup, and development commands.

# 6. Backend Architecture

DEVDOC adheres to strict architectural layering:

```
HTTP Request
     │
     ▼
API Layer (`app/api/v1/`)
     │  - Thin route handlers
     │  - URL parameter extraction & response serialization
     ▼
Security Dependencies (`app/dependencies.py`)
     │  - Supabase JWT cryptographic signature verification
     │  - Active user identity verification (`require_active_user`)
     │  - Project ownership enforcement (`require_project_access`)
     │  - Session claims propagation (`get_authenticated_db`)
     ▼
Service Layer (`app/services/`)
     │  - Pure business logic, invariants & state machine validation
     │  - Active run concurrency checks, boundary consistency
     │  - Structured audit logging
     ▼
Database Layer (`app/models/`, `app/db/`)
     │  - Async SQLAlchemy ORM sessions
     │  - Connection pooling with automatic claim reset
     ▼
PostgreSQL Engine with Supabase RLS
        - Database-level row isolation via `public.has_project_access(project_id)`
```

### Architectural Principles

- **Thin API Handlers**: Routers do not contain SQL queries or complex business logic. They delegate directly to the service layer.
- **Orchestrator Separation**: Investigation orchestration is implemented in backend/orchestrator/ and invoked through backend services.
- **Non-Bypassable RLS**: All queries pass through `get_authenticated_db`, ensuring PostgreSQL policies enforce boundaries even in the event of an application defect.

---

# 7. Security Architecture

### Authentication

- **Supabase JWT Integration**: Authenticated endpoints validate bearer tokens using `app.core.security.verify_supabase_jwt`.
- **Mandatory Signature Verification**: HMAC (HS256) and asymmetric JWKS public keys are verified strictly. Unsigned tokens or mismatched issuers/audiences are immediately rejected with HTTP 401.
- **UUID-Anchored Consistency**: Users are mapped strictly by the JWT `sub` claim matching `public.users.id`. Mutable identifiers (e.g., email) are never used as primary keys.

### Authorization

- **Project Boundary**: `require_project_access` verifies the authenticated user owns the target project (or is an active superuser). Non-owners receive HTTP 403 Forbidden.
- **Active Status Guard**: Deactivated users (`is_active = False`) are blocked from all endpoints by `require_active_user` with HTTP 403 Forbidden.

### PostgreSQL Row Level Security (RLS)

- **Session Context Injection**: `get_authenticated_db` executes `SET LOCAL request.jwt.claim.sub = :uid` within the request transaction.
- **Database-Enforced Policy**: Tables (`projects`, `incidents`, `investigations`, `repositories`, `user_github_connections`, `audit_logs`) enforce RLS policies via `public.has_project_access(project_id)`.
- **Zero Cross-User Leaks**: User A cannot read, insert, update, or delete User B's rows at the database engine level.

### Anti-Spoofing & Immutability

- **Authoritative URL Routing**: Resource ownership is determined by path parameters (`/projects/{project_id}/...`). Body-level `project_id` or `incident_id` injection is rejected.
- **Strict Schema Validation**: All write schemas use Pydantic `extra="forbid"`. Attempting to supply `id`, `project_id`, `created_at`, or `updated_at` returns HTTP 422 Unprocessable Entity.
- **Hierarchical Boundary Validation**: Every investigation request verifies that `incident_id` belongs to `project_id`, and that `investigation_id` belongs to `incident_id`.

### Secret Sanitization & Audit Logging

- **Zero Credential Exposure**: JWTs, GitHub access tokens, and OAuth secrets are never logged or returned in API responses.
- **Structured Audit Metadata**: Audit logs record timestamps, actor IDs, project IDs, incident IDs, investigation IDs, and status transition outcomes.
- **Approval and Audit Write Boundary**: Migration `0008_restrict_client_approval_audit_writes` removes direct authenticated-client approval creation/decision and audit-event insertion. Scoped reads remain; approval lifecycle audit entries are database-generated.
- **Deployment Caveat**: RLS does not constrain database owners or roles with `BYPASSRLS`. Use a server-only database identity, apply all migrations, and verify the runtime database role and proxy configuration for the deployment.

The Phase 19 audit summary, threat model, deployment assumptions, and known limitations are in [SECURITY.md](./SECURITY.md).

---

# 8. Database & Migrations

Database migrations are managed using Alembic. Historical migrations remain immutable:

| Migration                     | Revision                   | Description                                                                                                           |
| ----------------------------- | -------------------------- | --------------------------------------------------------------------------------------------------------------------- |
| `0001_initial_schema.py`      | `0001_initial_schema`      | Core schema: users, projects, repositories, incidents, investigations, evidence, fix proposals, approvals, audit logs |
| `0002_row_level_security.py`  | `0002_row_level_security`  | PostgreSQL Row Level Security policies, helper functions (`has_project_access`), table locks                          |
| `0003_github_connections.py`  | `0003_github_connections`  | GitHub OAuth connection table (`user_github_connections`) with RLS                                                    |
| `0004_incident_management.py` | `0004_incident_management` | Incident `source` enum, `detected_at` timestamps, composite query indexes                                             |
| `0005_investigation_api.py`   | `0005_investigation_api`   | Investigation `summary`, `started_at` timestamps, query indexes; cleans speculative AI fields                         |

### Running Migrations

```bash
# Apply all migrations to latest head
alembic upgrade head

# Roll back the most recent migration
alembic downgrade -1

# Re-apply migrations
alembic upgrade head
```

---

# 9. Implemented Backend Phases

### Phase 5 — Authentication & Authorization

- Validates Supabase JWTs cryptographically; enforces user mapping to verified `sub` claims.
- Provides authenticated database sessions via `get_authenticated_db` to propagate session context to PostgreSQL RLS.

### Phase 6 — User & Project APIs

- Implements profile management (`/users/me`) and project CRUD (`/projects`).
- Prevents spoofing via `extra="forbid"`, automatically anchors `owner_id`, and cascades deletion to child resources.

### Phase 7 — GitHub Integration

- Implements secure GitHub OAuth connection with signed HMAC CSRF state.
- Provides project repository attachment and inspection endpoints (branches, commits, PRs, issues, files, workflows).
- Enforces strict credential masking (access tokens are never logged or returned in responses).

### Phase 8 — Incident Management

- Implements operational incident lifecycle: `OPEN` → `INVESTIGATING` → `MITIGATED` → `RESOLVED` → `CLOSED`.
- Provides bounded pagination (max 100), deterministic sorting (`created_at DESC`), and filtering by status, severity, and source.

### Phase 9 — Investigation API

- Implements the investigation API data contract and finite state machine.
- Enforces active-investigation concurrency limits (HTTP 409 if a run is already active).
- Validates dual project and incident boundaries, tracks execution timestamps (`started_at`, `completed_at`), and prepares token/cost tracking for Phase 13.

---

# 10. Phase 7 — GitHub Integration

Phase 7 connects DEVDOC to GitHub repositories for investigation context:

```
User Browser ────► GET /api/v1/github/connect ────► Redirect to GitHub (Signed CSRF State)
                                                           │
User Authorizes ◄──────────────────────────────────────────┘
      │
      ▼
GET /api/v1/github/callback?code=...&state=...
      │  - Validates HMAC state signature & expiration
      │  - Exchanges code for access token via GitHub API
      │  - Persists UserGitHubConnection with PostgreSQL RLS
      ▼
Safe Response (Token masked, connected=True)
      │
      ▼
POST /api/v1/projects/{project_id}/github/repository
      │  - Verifies project ownership
      │  - Verifies authenticated user has access to target repository
      ▼
Attached Repository ready for inspection (commits, PRs, workflows, contents)
```

- **Anti-SSRF & Input Validation**: All repository requests go through typed client methods with strict owner/repository format validation. Path traversal (`..`) in contents queries is rejected.
- **Rate Limit Handling**: GitHub API rate limits (HTTP 429) and upstream errors are caught and transformed into structured application error responses.

---

# 11. Phase 8 — Incident Management

### Incident Lifecycle State Machine

```
                  ┌──────────────┐
                  │     OPEN     │◄────────────┐
                  └──────┬───────┘             │
                         │                     │ (Reopen)
                         ▼                     │
                  ┌──────────────┐             │
           ┌─────►│INVESTIGATING ├─────────────┤
           │      └──────┬───────┘             │
(Recovery) │             │                     │
           │             ▼                     │
           │      ┌──────────────┐             │
           └──────┤  MITIGATED   ├─────────────┤
                  └──────┬───────┘             │
                         │                     │
                         ▼                     │
                  ┌──────────────┐             │
                  │   RESOLVED   ├─────────────┘
                  └──────┬───────┘
                         │
                         ▼
                  ┌──────────────┐
                  │    CLOSED    │
                  └──────────────┘
```

- **Controlled Transitions**: Validated in `IncidentService.validate_status_transition`. Arbitrary jumps (e.g., `OPEN` → `CLOSED`) raise HTTP 422.
- **Controlled Enums**:
  - Severity: `low`, `medium`, `high`, `critical`, `info`
  - Source: `manual`, `github`, `monitoring`, `webhook`, `system`
- **Automated Bookkeeping**: `resolved_at` is automatically recorded when transitioning into `RESOLVED` or `CLOSED`, and cleared if reopened.

---

# 12. Phase 9 — Investigation API

Phase 9 establishes the investigation data contract and execution lifecycle.

### Investigation Lifecycle State Machine

```
                  ┌──────────────┐
                  │   PENDING    │─────────────┐
                  └──────┬───────┘             │
                         │                     │ (Cancel)
                         ▼                     │
                  ┌──────────────┐             │
                  │   RUNNING    │─────────────┤
                  └──────┬───────┘             │
                         │                     │
                ┌────────┴────────┐            │
                │                 │            ▼
                ▼                 ▼     ┌──────────────┐
         ┌──────────────┐  ┌──────────┐ │  CANCELLED   │
         │  COMPLETED   │  │  FAILED  │ └──────────────┘
         └──────────────┘  └──────────┘
```

- **Allowed Transitions**:
  - `PENDING` → `RUNNING`, `CANCELLED`
  - `RUNNING` → `COMPLETED`, `FAILED`, `CANCELLED`
  - `COMPLETED`, `FAILED`, `CANCELLED` are terminal states (idempotent same-state updates allowed).
  - Invalid transitions raise HTTP 422 Unprocessable Entity.
- **Active-Investigation Concurrency Rule**: Only **one** active investigation (`PENDING` or `RUNNING`) can exist per incident at any time. Attempting to create a second concurrent active investigation returns HTTP 409 Conflict. Once completed, failed, or cancelled, subsequent investigations can be created.
- **Timestamp & Lifecycle Tracking**:
  - `started_at` is automatically populated when entering `RUNNING`.
  - `completed_at` is automatically populated when entering `COMPLETED`, `FAILED`, or `CANCELLED`.
  - `error_message` records failure reasons when transitioning to `FAILED`.
- **Token & Cost Budgeting Foundation**:
  - `tokens_used`: Integer tracking tokens consumed (defaults to `0`, non-negative constraint).
  - `estimated_cost_usd`: Integer tracking cost in micro-USD (defaults to `0`, non-negative constraint).
- **Architectural Boundaries**:
  - Speculative AI/result fields (`root_cause_summary`, `confidence_score`) were intentionally excluded from Phase 9. AI diagnostic synthesis belongs to Phase 15.

---

# 13. Investigation Pipeline: Phases 10+

> **Status: Phases 10–18 implemented; sandbox verification and approval-artifact persistence are opt-in**

Chat history (Phase 16.1) is persisted alongside the investigation pipeline. It is incident-scoped and can reference an investigation, but does not gate or replace evidence collection, diagnosis, fix generation, or verification.

When triggered, an investigation will execute the autonomous AI pipeline:

```
Incident Detected
       │
       ▼
Investigation Created (PENDING → RUNNING)
       │
       ▼
DEVDOC Orchestrator [Phase 10]
  Dispatches concurrent telemetry, GitHub, and container inspection agents
       │
       ▼
Evidence Engine [Phase 12]
  Collects logs, error traces, diffs, metrics snapshots, and workflow runs
       │
       ▼
Tavily Knowledge Search [Phase 14]
  Retrieves vendor documentation, known issue solutions, and CVE databases
       │
       ▼
NVIDIA Nemotron 70B via Nebius [Phase 13]
  Reasons over structured evidence, context timeline, and external knowledge
       │
       ▼
Root Cause Engine [Phase 15]
  Synthesizes root cause diagnosis with ranked hypotheses and confidence score
       │
       ▼
Fix Generator [Phase 16]
  Produces validated, unexecuted proposals; never applies patches or runs commands
       │
       ▼
Sandbox Verification [Phase 17]
  Optionally executes trusted configured checks against the Phase 16 proposal in an isolated sandbox
       │
       ▼
Human Approval Gate [Phase 18]
  Authorized human reviews the diagnosis, proposal, and exact passing sandbox result
       │
       ▼
Production Resolution [Not implemented]
  No approval endpoint applies a patch, deploys, or changes incident state
```

---

# 14. AI Reasoning and Knowledge Search

> **Status: Implemented — Phase 13 (opt-in; no model call at startup or in tests)**

## Phase 13 — NVIDIA / Nebius Reasoning and Cost Control

Phase 13 consumes the normalized Phase 12 evidence collection and returns structured observations, explicit uncertainties, and follow-up questions. Its output is evidence-referenced and is not a root-cause diagnosis or a fix proposal.

- **Provider boundary**: `LLMProvider` separates provider-neutral orchestration from the Nebius OpenAI-compatible Nemotron adapter. A deterministic fake provider is used in automated tests.
- **Explicit opt-in**: `LLM_ENABLED=false` by default. No model client is constructed, and no outbound LLM call occurs during imports, application startup, health checks, local tests, or CI. To use the provider, explicitly construct it with `create_nebius_llm_service(settings)` and inject that service into `DEVDOCOrchestrator` or an operational stage registry.
- **Budget cap**: Each outbound attempt first reserves its worst-case input/output cost against a maximum configured budget of $25. The factory uses an atomic SQLite ledger (default `backend/.devdoc-llm-budget.sqlite3`) so spend and in-flight reservations survive restarts and are shared by processes using the same local filesystem. Failed or crash-interrupted attempts consume their reservation because provider-side billing may be unknown. SQLite does not coordinate separate hosts; multi-host live inference requires a shared transactional budget store, which is outside this phase.
- **Pricing configuration**: Set both `LLM_INPUT_COST_PER_MILLION_USD` and `LLM_OUTPUT_COST_PER_MILLION_USD` to the current price for the configured Nebius model before enabling requests. Zero/unset rates cause service construction to fail closed; estimates are not a provider invoice.
- **Token and request bounds**: UTF-8 request size is conservatively bounded by the configured input-token limit; output tokens, HTTP timeout, retries (maximum three), and exponential backoff are also capped.
- **Cache**: Successful structured results are kept in a bounded in-memory TTL cache. Cache hits make no provider request and have zero additional token cost.
- **Response safety**: Provider JSON is validated against strict Pydantic contracts. Every referenced evidence ID must belong to the submitted evidence set. Evidence text is sanitized and treated as untrusted data.
- **Observability**: Results include provider/model, request ID, duration, attempts, input/output token counts, estimated spend, budget remaining, and cache-hit status. Prompts and credentials are excluded.
- **Secret handling**: The Nebius API key is a `SecretStr`, sent only in the server-side HTTPS Authorization header, and never included in logs or error messages.

See `backend/.env.example` for the complete Phase 13 configuration. Do not enable live inference without setting current Nebius token prices and explicitly injecting the configured service.

## Phase 14 — Knowledge Search / Tavily

> **Status: Implemented — opt-in; automated tests use fake providers or HTTPX mock transports**

Phase 14 adds a provider-neutral search service with a Tavily adapter. `AnalyzeStage` can search after evidence collection and before the optional LLM reasoning call. Search is only available when a `KnowledgeSearchService` is explicitly constructed and injected; the default application workflow does not construct it or make search calls.

- **Bounded query and results**: Queries are built from allow-listed investigation/evidence fields, sanitized, and length-limited. Search depth, result count, response size, title/content/URL lengths, timeout, retries, concurrency, per-investigation usage, and cache capacity are configurable and validated.
- **Safe provider boundary**: The adapter calls Tavily over HTTPS, keeps `TAVILY_API_KEY` server-side, requests neither generated answers nor raw page content, and never follows result URLs. Returned URLs are accepted only after HTTPS and host validation; private/local destinations and non-allow-listed domains (when configured) are rejected.
- **Evidence provenance and trust**: Search results are normalized and merged through the Phase 12 Evidence Engine with provider, query, URL, retrieval timestamp, and an `untrusted_external` classification. These references are not observed incident facts. The Phase 13 reasoning prompt explicitly treats page text as untrusted and preserves source links.
- **Failure behavior**: A search failure preserves collected evidence, marks analysis as failed, and skips LLM reasoning for that stage. The orchestrator's existing `FAIL_FAST` or `CONTINUE_ON_FAILURE` workflow policy controls downstream stages.
- **Caching and process-local limits**: A bounded TTL cache is scoped to project, investigation, execution, and query. Usage limits and concurrency controls are held in memory per service instance; they are not durable or shared across hosts.
- **Phase boundary**: This phase retrieves and attributes references only. It does not diagnose root cause, generate fixes, fetch arbitrary pages, run commands, verify changes, or perform remediation.

Search remains disabled unless `KNOWLEDGE_SEARCH_ENABLED=true`, a server-side `TAVILY_API_KEY` is configured, and the service is explicitly injected. See `backend/.env.example` for the bounded controls. Phase 14 tests use fake providers and `httpx.MockTransport`; no automated test or startup path makes a live Tavily or Nebius request.

## Phase 15 — Root Cause Analysis Engine

> **Status: Implemented — analysis-only; Nemotron remains opt-in**

Phase 15 evaluates ranked incident-specific hypotheses from the Phase 12 evidence collection, Phase 13 reasoning (when available), Phase 14 external references, and the existing timeline/correlation graph. It is integrated into `DiagnoseStage` through an explicitly injected `RootCauseAnalysisService`; the default application does not construct an LLM or make inference calls.

- **Evidence-grounded contract**: The output separates recorded `FACT` evidence references from `EXTERNAL_KNOWLEDGE`. Every candidate is explicitly classified as a `HYPOTHESIS` and must cite at least one actual observed evidence ID. Summary and hypothesis-chain claims require valid evidence references; unknown or fabricated evidence and correlation IDs fail validation.
- **Hypothesis chain**: Candidates may describe contributing factors, triggering events, and observed symptoms separately. Phase 12 timeline and correlation IDs are provided as context; temporal order and correlation are not treated as causation.
- **Contradictions and uncertainty**: Candidates include supporting and contradicting evidence plus uncertainties. Deterministic ranking uses unique observed evidence items, independent evidence sources, and observed contradictions; repeated IDs cannot inflate evidence strength. A tie among plausible candidates is returned as `multiple_plausible_causes`.
- **Confidence and selection**: `LOW` means evidence is sparse, dependent, or contradicted; `MEDIUM` means at least two unique observations from two sources support the candidate and contradictions are fewer than supports; `HIGH` requires at least three unique observations from two sources and no observed contradiction. These are qualitative evidence tiers, not probabilities. Only a uniquely strongest `HIGH` candidate is selected; a weaker or tied result remains unselected.
- **Missing information**: The result identifies discriminating evidence to collect next. With no evidence, the stage returns `insufficient_evidence` without an LLM call.
- **Prompt and output safety**: Evidence, logs, model reasoning, and external content are delimited as untrusted data. The prompt forbids following embedded instructions, inventing facts/IDs/URLs/timestamps, or proposing fixes. Strict Pydantic validation checks schema, category enums, evidence IDs, temporal relationship IDs, and generated URLs before accepting output.
- **LLM, budgets, and cache**: RCA uses `LLMService.complete_structured`, reusing Phase 13's provider, global budget guard, token bounds, retry/timeout controls, safe observability, and bounded in-memory cache. Cache keys include project, investigation, execution, model, and the full sanitized prompt. An in-memory per-service limit allows at most three RCA analyses per project/investigation; usage limits are not shared across hosts.
- **Failure and cancellation**: Budget, provider, timeout, schema, and reference failures are surfaced as a failed diagnosis stage and follow the configured orchestrator failure policy. Cancellation is checked before requests and retries; if requested while a provider call is in flight, the active request may complete, but no further retry is started and the result is not accepted.
- **No persistence or actions**: Analysis is returned in the orchestration stage result; it does not mutate evidence or add database tables/migrations. There is no public RCA endpoint. Phase 15 does not generate patches, commands, or fixes, execute operations, modify production or GitHub, or bypass approval.

All Phase 15 automated tests use a fake provider. There is no real-model smoke test enabled by default; a real request occurs only when an operator explicitly constructs and injects the configured Nebius service, and it consumes the existing Phase 13 budget.

## Phase 15 — Fix Generator

> **Status: Implemented — opt-in proposals only; no remediation is executed**

`FixGeneratorService` is injected into `ProposeFixStage` and accepts only the current validated Phase 15 `RootCauseAnalysis` and matching Phase 12 `EvidenceCollection`. It returns `insufficient_information` without a model request unless the RCA uniquely selected a root cause with observed supporting evidence. The default stage registry has no fix generator injected and remains offline.

- **Proposal contract**: `FixProposal` includes the selected root-cause ID, investigation and execution IDs, summary, evidence references, affected components, change type, proposed changes, prerequisites, risks, confidence, verification steps, rollback plan, generation time, and safe model usage metadata. Every result requires human approval; any code diff is marked `PROPOSED / UNVERIFIED`.
- **Evidence and reference checks**: Root-cause identity and RCA evidence references are checked against the active analysis and evidence snapshot. Each change must cite observed evidence supporting the selected cause. External knowledge IDs must resolve to external evidence, and external content is explicitly marked untrusted in the prompt.
- **Patch and secret safety**: File targets are accepted only when an exact repository-relative path is present in inspected-file evidence. Absolute paths, traversal, unverified targets, binary or oversized diffs, excessive changed lines, recognized secret patterns, and recognized destructive operations are rejected without returning a proposal.
- **Risk, rollback, and verification**: Database, dependency, infrastructure, and deployment changes have a deterministic minimum HIGH risk. HIGH, CRITICAL, and UNKNOWN risks require human review; all statuses remain proposals. Rollback and measurable verification plans are mandatory.
- **Cost and cancellation**: Uses the injected Phase 13 `LLMService` for the existing global budget, token bounds, retries, timeout, TTL cache, and cancellation checks. A per-investigation generation-count limit bounds repeated proposals. No separate provider, cache, or monetary budget system is created.
- **No execution or persistence**: There is no public fix endpoint, persistence, migration, GitHub write, shell execution, production access, deployment, or patch application. Phase 16 returns inert data for future Phase 17 sandbox integration; it does not implement sandbox verification or Phase 18 approval.
- **Testing**: Automated tests use fake providers only. They do not call Nebius or Tavily and consume no AI credits.

---

## Phase 16.1 — Chat History

> **Status: Implemented — durable conversation/message storage; no chat model call**

Conversations are scoped to a project and incident and may optionally reference an investigation. User and assistant messages are persisted in chronological order. The feature provides paginated history, conversation listing, rename, and delete operations; it does not itself generate assistant responses or call an LLM.

- **API**: Authenticated endpoints under `/api/v1/projects/{project_id}/incidents/{incident_id}/conversations`. Conversation reads/writes validate project and incident boundaries; an optional investigation must belong to that same incident and project.
- **Database**: Alembic migration `0006_chat_history` creates `chat_conversations` and `chat_messages`, with project-scoped RLS, bounded message/title sizes, indexes, cascading cleanup, and a composite conversation/project foreign key for messages.
- **Contract**: Only `user` and `assistant` roles are accepted; writes reject blank content and extra fields. Pagination is capped at 100 records.
- **Integration boundary**: Chat history may retain context for prior Phase 15 diagnosis, Phase 16 proposals, and Phase 17 verification, but does not alter those contracts or execute actions.

## Phase 16 — Sandbox Verification

> **Status: Implemented — opt-in; Docker execution was not exercised during implementation**

`SandboxVerificationService` consumes a validated Phase 16 `FixProposal`, copies a bounded repository workspace into a disposable temporary workspace, applies proposed file-state changes or a single-file unified diff, and evaluates expected results against bounded output from explicitly injected trusted argv commands.

- **Provider boundary**: `SandboxProvider` separates orchestration from execution. `FakeSandboxProvider` supports deterministic tests. `DockerSandboxProvider` requires a digest-pinned, already-local image; it does not pull images.
- **Isolation**: Docker runs with `--network none`, a read-only root filesystem, non-root UID, all Linux capabilities dropped, `no-new-privileges`, CPU/memory/process limits, and bounded tmpfs for workspace and temporary files. The source is copied into tmpfs; no host paths, Docker socket, host environment, ports, credentials, or production network are passed to the container.
- **No command generation**: Verification commands are configured/injected separately from model-generated proposal text, validated as argv (never `shell=True`), and restricted to an executable allow-list. If there is no authorized source workspace, no trusted command mapping, or expected output cannot be observed, the result is `INCONCLUSIVE`.
- **Safety and cleanup**: Workspace copying omits VCS metadata and credential paths; symlinks, traversal, absolute paths, sensitive targets, and unsupported patches are rejected. Execution and output are bounded. Provider cleanup runs after normal completion, failure, timeout, or cancellation; labeled stale containers can be removed through explicit orphan cleanup.
- **Result**: Typed outcomes include `PASSED`, `FAILED`, `INCONCLUSIVE`, `TIMEOUT`, `CANCELLED`, `UNSAFE`, and `SETUP_FAILED`. Results are carried in the orchestrator VERIFY stage/context; no verification database table, public execution API, new LLM call, GitHub write, or production action is added.

## Phase 17 — Human Approval & Audit

> **Status: Implemented — approval is human-only; no remediation execution**

Phase 18 lets an authorized project owner or platform administrator review a fix proposal only after a complete Phase 17 sandbox verification has passed. Approval is a recorded decision, not an instruction that executes or deploys the proposal.

- **Verified review bundle**: When the optional trusted artifact recorder is injected, the server persists immutable RCA, proposal, and verification snapshots with SHA-256 fingerprints. Requests bind to both the exact proposal and passing verification; the live stored proposal is checked again before a decision.
- **Eligibility and lifecycle**: A selected supported RCA and matching proposal are required. Every verification step must pass, cleanup must complete, and the proposal must be no older than seven days. Pending requests expire after 24 hours; stale or expired requests cannot be approved, and terminal decisions cannot be replayed.
- **Authorization and API**: Authenticated routes are under `/api/v1/projects/{project_id}/investigations/{investigation_id}/approvals` for request creation/listing, review, approve, reject, cancel, and audit history. The actor is always derived from authentication. Project owners and platform administrators may review; the requester may cancel, and platform administrators may cancel on their behalf.
- **Audit and database protections**: Migration `0007_human_approval_audit` adds project-scoped RLS, approval-state constraints, concurrency protection, immutable artifact/audit rows, transition guards, and database-generated lifecycle audit events. Approval requests cannot be deleted.
- **Orchestration boundary**: The VERIFY stage only persists review artifacts when a trusted recorder is explicitly injected. A passing result marks the proposal as awaiting human review; it does not itself approve anything. The default pipeline does not enable a sandbox provider or recorder.
- **No production action**: There is no patch application, GitHub write, deployment, rollback, or incident resolution in this phase. Sandbox and approval tests use local fixtures; they do not execute production operations.

## Phase 18 — Security Hardening

> **Status: Targeted changes implemented — database write-boundary hardening only; broader security controls are not certified**

Migration `0008_restrict_client_approval_audit_writes` closes authenticated-role direct writes that could forge audit events or record approval decisions without the service's verification eligibility checks. It preserves project-scoped reads and database-generated approval lifecycle events. See [SECURITY.md](./SECURITY.md) for the audit findings, threat model, deployment assumptions, tested scope, and remaining limitations. Apply migrations through the latest revision; PostgreSQL integration tests require an isolated test database.

## Phase 19 — API Rate Limiting

> **Status: Implemented — configure shared Redis before production deployment**

- **Tenant quotas**: Authenticated API routes are limited by the verified JWT `sub` (the user account). This is the current tenant boundary because the schema has users and projects, but no organization/tenant entity. Default token bucket capacity is 120 requests, replenished at 2 requests per second.
- **Burst protection**: All non-health/readiness HTTP routes also use a source-IP bucket with capacity 120 and refill of 10 requests per second. `/api/v1/health` and `/api/v1/ready` are exempt for load-balancer probes. GitHub's signed OAuth callback is covered by the IP bucket; other authenticated GitHub routes also receive the tenant quota.
- **Distributed enforcement**: Redis Lua token buckets use Redis server time and atomic updates, so concurrent app workers share quotas. Rejections return HTTP 429 with `Retry-After`, `X-RateLimit-Limit`, and `X-RateLimit-Remaining` headers.
- **Failure behavior**: Production settings require rate limiting to remain enabled and `RATE_LIMIT_REDIS_URL` to be configured. Redis connection/ping failures prevent startup; the limiter does not fail open. Local development can use the bounded in-memory backend, which is process-local and must not be used as a production substitute.
- **Operations**: Set `RATE_LIMIT_REDIS_URL` to a private, authenticated Redis endpoint and tune the capacities/refill rates in the environment. If running behind a reverse proxy, configure the ASGI server's trusted proxy list so source-IP protection uses the actual client address; never trust arbitrary forwarded-for headers.

# 15. Local Development

### Prerequisites

- Python 3.13 or higher
- Node.js and npm (for the frontend)
- Docker (for local PostgreSQL / Supabase testing)
- Git

### Setup Instructions

```bash
# 1. Clone the repository
git clone https://github.com/DEVDOC-Team/devdoc.git
cd devdoc/backend

# 2. Create and activate a Python virtual environment
python -m venv .venv

# Windows (PowerShell):
.venv\Scripts\Activate.ps1

# macOS / Linux:
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt

# 4. Configure environment variables
cp .env.example .env
# Edit .env with your local database credentials and Supabase JWT secret

# 5. Run database migrations
alembic upgrade head

# 6. Start the development server
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

---

### Frontend development

In a second terminal, run these commands from the frontend directory:

    npm ci
    Copy-Item .env.example .env
    npm run dev

Vite serves the app at http://localhost:5173 by default. Local development uses a FastAPI backend at http://localhost:8000. For shared deployments, set VITE_API_BASE_URL to a backend URL reachable by each browser (or use same-origin reverse proxying) and configure backend CORS_ORIGINS for the frontend origin. A localhost API URL only reaches the computer running the browser. See frontend/README.md for details.

---

# 16. Testing & Quality

DEVDOC maintains an asynchronous test suite covering unit logic, REST endpoints, security boundaries, and PostgreSQL Row Level Security.

### Running Tests

```bash
cd backend

# Run the complete test suite
python -m pytest -v

# Run Phase 8 Incident tests
python -m pytest tests/test_phase8_incidents.py -v

# Run Phase 9 Investigation tests
python -m pytest tests/test_phase9_investigations.py -v

# Run static analysis and linting
python -m ruff check .
```

> **Backend verification snapshot (October 25, 2026):** 482 passed, 14 skipped, and 0 failures. The complete report and its environment details are in BACKEND_VERIFICATION_REPORT.md.

---

# 17. Docker

A containerized runtime is provided via `backend/Dockerfile` for local integration and testing:

```bash
# Build the backend container
docker build -t devdoc-backend -f backend/Dockerfile backend/

# Run an ephemeral PostgreSQL 16 container for testing
docker run --name devdoc-postgres \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=devdoc_test \
  -p 5433:5432 \
  -d postgres:16-alpine

# Apply the schema to this disposable test database
cd backend
export DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:5433/devdoc_test"
export DIRECT_DATABASE_URL=""
python -m alembic upgrade head
cd ..

# Run the PostgreSQL RLS and approval-trigger integration tests
export TEST_POSTGRESQL_URL="postgresql://postgres:postgres@localhost:5433/devdoc_test"
python -m pytest backend/tests/test_rls_security.py -v
```

The PostgreSQL RLS tests skip when `TEST_POSTGRESQL_URL` is unavailable. Use only a disposable local database for this test suite; its fixtures create records in the configured database.

---

# 18. Team & Ownership

DEVDOC is built and maintained by a 5-member engineering team:

| Member       | Role                            | Primary Responsibilities                                                                |
| ------------ | ------------------------------- | --------------------------------------------------------------------------------------- |
| **Member 1** | Backend / API                   | FastAPI endpoints, routing, schemas, API versioning, business services                  |
| **Member 2** | Database / Auth                 | PostgreSQL schema, SQLAlchemy models, Supabase RLS, JWT authentication                  |
| **Member 3** | AI / Agent                      | Orchestrator package, evidence collection, Nemotron/Nebius reasoning, root cause engine |
| **Member 4** | DevOps / Integrations / Sandbox | GitHub OAuth, containerization, Docker sandbox verification, CI/CD pipelines            |
| **Member 5** | Security / QA / Operations      | Security audit, vulnerability review, load testing, telemetry, test coverage            |

---

# 19. Git Workflow

DEVDOC uses a structured Git branching strategy to guarantee stability:

```
prd  (Production releases)
 ▲
 │ Pull Request
dev  (Integration & staging)
 ▲
 │ Pull Request
features  (Approved phase integration baseline)
 ▲
 │ Pull Request
feature/phase-X  (Scoped feature branches)
```

- `prd`: Production-ready code. Merges occur only from `dev` after full release validation.
- `dev`: Active development integration. Merges occur from `features` after integration sign-off.
- `features`: Approved phase integration baseline. Completed phase branches PR into `features`.
- `feature/*`: Scoped branches for individual development phases (e.g., `feature/phase9-investigation-api`).

---

# 20. Development Rules

1. **Strict Branch Scoping**: Each pull request must address exactly one development phase or feature. Unrelated modifications are prohibited.
2. **Mandatory Quality Gates**: Every branch must pass `python -m ruff check .` and the complete `python -m pytest -v` regression suite before PR creation.
3. **No Secret Commits**: Never commit `.env` files, API keys, private tokens, or credentials. Use `.env.example` placeholders.
4. **Thin API Routing**: Business logic must reside in `app/services/`, not inside FastAPI route handlers.
5. **Defense in Depth**: Always enforce authorization at the application layer (`dependencies.py`) and verify database-level isolation via PostgreSQL RLS.

---

# 21. Hackathon Submission & Demo Runner

### Nebius x NVIDIA Hackathon Highlights

- **Inference Provider**: Nebius Token Factory (`https://api.studio.nebius.ai/v1`)
- **NVIDIA Models Supported**: `nvidia/Nemotron-3_5-Lightning`, `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B`
- **Cost & Budget Enforcement**: Conservative SQLite-backed `LLMBudgetGuard` tracking exact micro-dollar spend ($0.06 / 1M input tokens, $0.24 / 1M output tokens).
- **Mandatory Human-in-the-Loop Gate**: Remediation proposals are verified in ephemeral sandboxes and cryptographically fingerprinted via SHA-256 before human review. **Zero automated production deployments or bypasses.**

### Running the Investigation Demo

#### 1. Deterministic Demo Mode (Offline Safe, No Billing)

Executes the full pipeline from incident creation, multi-modal evidence collection, RCA, fix proposal, sandbox verification, and human approval gating:

```bash
cd backend
python scripts/demo_investigation.py --mode=demo
```

#### 2. Live Nebius Inference Mode (Real NVIDIA Nemotron API Call)

Validates live external connectivity to Nebius Token Factory, model discovery, token accounting, and live structured reasoning:

```bash
cd backend
python scripts/demo_investigation.py --mode=live
```

### Running the Backend REST API

```bash
cd backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

### Triggering an Investigation via REST API

```http
POST /api/v1/projects/{project_id}/incidents/{incident_id}/investigations/{investigation_id}/run
Authorization: Bearer <supabase_jwt>
```

---

# 22. License

Proprietary / Internal project license. All rights reserved. DEVDOC Team.

LIVE DEMO🔗=
