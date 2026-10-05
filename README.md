# DEVDOC

**DEVDOC** is an AI-powered DevOps and SRE incident investigation and remediation platform. It provides development and operations teams with an automated, evidence-grounded pipeline to investigate operational outages, analyze system telemetry, diagnose root causes, and generate verified fixes with human-in-the-loop approval.

> **Current Status**: Phases 1–15 are implemented, including opt-in Nemotron/Nebius reasoning, Tavily knowledge search, and evidence-grounded root-cause analysis. Phase 16+ is upcoming.

---

# 1. Overview

## What is DEVDOC?

DEVDOC automates the end-to-end operational incident lifecycle through a secure, structured investigation pipeline:

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
Resolve
```

* **Implemented Today (Phases 1–15)**: Production-grade backend foundation, Supabase database models, Row Level Security (RLS) policies, JWT authentication, user and project management, GitHub OAuth and repository inspection, incident management, the investigation orchestrator, operational agents, the bounded evidence engine, opt-in structured Nemotron/Nebius reasoning, opt-in Tavily knowledge search, and evidence-grounded root-cause analysis.
* **Planned (Phase 16+)**: Fix generation, sandbox verification, and interactive human-in-the-loop approval gates.


## Why DEVDOC?

* **Fragmented Operational Context**: Logs, metrics, stack traces, and GitHub commit history are scattered across disparate tools, slowing down triage during critical outages.
* **Cognitive Overload Under Fire**: Engineers manually piece together timeline events under severe time pressure, leading to diagnostic errors and extended downtime.
* **Context Blindness**: Traditional observability dashboards display alerts but lack direct awareness of repository code, recent pull requests, or CI/CD workflow failures.
* **Unsafe Automation**: Blind automated remediation risks catastrophic secondary outages without isolated sandbox verification and explicit human approval.

---

# 2. Architecture

The high-level DEVDOC platform architecture enforces strict separation between API handling, database persistence, and future autonomous AI orchestration:

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
                 Fix Generator             [Phase 16 — Planned]
                       │
                       ▼
             Sandbox Verification          [Phase 17 — Planned]
                       │
                       ▼
             Human Approval Gate           [Phase 18 — Planned]
                       │
                       ▼
             Production Resolution         [Phase 18 — Planned]
```

---

# 3. Technology Stack

### Current Implementation (Phases 1–9)

| Layer | Technology | Purpose |
|---|---|---|
| Language | Python 3.13+ | Modern backend runtime |
| API Framework | FastAPI | High-performance asynchronous REST endpoints |
| ASGI Server | Uvicorn | Asynchronous HTTP server |
| Request/Response Validation | Pydantic v2 | Strict schema validation with `extra="forbid"` |
| Settings & Config | pydantic-settings | Type-safe environment variable management |
| ORM & Queries | SQLAlchemy 2.0 (Async) | Asynchronous PostgreSQL persistence layer |
| Database & Auth | PostgreSQL 16 / Supabase | Relational store with Row Level Security (RLS) |
| Database Migrations | Alembic | Version-controlled database schema migrations |
| Testing | pytest + pytest-asyncio + HTTPX | Asynchronous unit, integration, and security test suite |
| Code Quality & Linting | Ruff | High-performance static analysis and formatting |
| Containerization | Docker | Reproducible containerized runtimes |

### Future Technologies (Phases 15+)

| Component | Planned Technology | Target Phase |
|---|---|---|
| Root cause diagnosis | Evidence-grounded causal analysis (opt-in Nemotron) | Phase 15 |
| Fix generation | Validated patch/configuration proposals | Phase 16 |
| Sandbox Execution | Isolated Docker / MicroVM Environments | Phase 17 |
| Human approval and audit | Controlled approval and resolution workflow | Phase 18 |

---

# 4. Project Status / Roadmap

DEVDOC is being delivered across 26 systematic development phases. Phases 1 through 9 establish the complete production-grade backend and data foundation.

| Phase | Status | Title | Description |
|:---:|:---:|---|---|
| 1 | ✅ Complete | Backend Foundation | FastAPI application structure, configuration, health endpoints, logging |
| 2 | ✅ Complete | Supabase Database Foundation | PostgreSQL connection pooling, async engine, base schema |
| 3 | ✅ Complete | Database Models & Relationships | Full relational schema for Users, Projects, Repositories, Incidents, Investigations |
| 4 | ✅ Complete | Supabase Row Level Security | PostgreSQL RLS policies, `has_project_access` security functions |
| 5 | ✅ Complete | Authentication & Authorization | Supabase JWT verification, session claim propagation, profile sync |
| 6 | ✅ Complete | User & Project REST APIs | User profile endpoints, project CRUD, anti-spoofing ownership boundaries |
| 7 | ✅ Complete | GitHub Integration | GitHub OAuth, signed CSRF state, repository attachment, code/commit/PR inspection |
| 8 | ✅ Complete | Incident Management | Operational incident model, controlled 5-state lifecycle, bounded pagination |
| 9 | ✅ Complete | Investigation API | Investigation data contract, finite state machine, dual boundary validation |
| 10 | ✅ Complete | DEVDOC Orchestrator | Autonomous agent orchestrator package, workflow coordination |
| 11 | ✅ Complete | Investigation Agents | Specialized GitHub, Docker, and Monitoring inspection agents |
| 12 | ✅ Complete | Evidence Engine | Bounded evidence normalization, validation, deduplication, timeline assembly, and graph correlation |
| 13 | ✅ Complete | NVIDIA Nemotron + Nebius | Provider abstraction, structured evidence reasoning, budget guardrails, token/cost tracking |
| 14 | ✅ Complete | Knowledge Search / Tavily | Bounded, opt-in external knowledge retrieval with provenance |
| 15 | ✅ Complete | Root Cause Engine | Evidence-referenced hypotheses, contradictions, confidence, and cautious cause selection |
| 16 | ⏳ Planned | Fix Generator | Automated patch generation, configuration remediation diffs |
| 17 | ⏳ Planned | Sandbox Verification | Isolated container execution, test validation of proposed fixes |
| 18 | ⏳ Planned | Human Approval & Audit | Interactive approval workflow, immutable audit trail, resolution |
| 19 | ⏳ Planned | Security Hardening | Rate limiting, header security, advanced secret sanitization |
| 20 | ⏳ Planned | API Rate Limiting | Tenant-based request quotas, burst protection |
| 21 | ⏳ Planned | Observability | Prometheus metrics, OpenTelemetry distributed tracing |
| 22 | ⏳ Planned | Load Testing | Locust stress testing, database concurrency validation |
| 23 | ⏳ Planned | Docker & CI/CD | Production multi-stage Docker builds, GitHub Actions CI/CD |
| 24 | ⏳ Planned | Production Architecture | Multi-region deployment, read replicas, caching tier |
| 25 | ⏳ Planned | Complete Backend Evaluation | Comprehensive end-to-end evaluation and verification suite |
| 26 | ⏳ Planned | Complete Documentation | Final architecture manuals, API specifications, operator runbooks |

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
│   │   │       └── versions/     # Versioned migration scripts (0001–0005)
│   │   ├── models/               # SQLAlchemy ORM models
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
│   │   │   ├── auth.py
│   │   │   ├── github.py
│   │   │   ├── health.py
│   │   │   ├── incident.py
│   │   │   ├── investigation.py
│   │   │   ├── project.py
│   │   │   ├── ready.py
│   │   │   └── user.py
│   │   └── services/             # Business logic layer
│   │       ├── auth.py
│   │       ├── github.py
│   │       ├── incident.py
│   │       ├── investigation.py
│   │       ├── project.py
│   │       └── user.py
│   ├── orchestrator/
│   │   ├── evidence/             # Phase 12 evidence engine and contracts
│   │   ├── llm/                  # Phase 13 provider, service, cache, and budget guard
│   │   └── tests/                # Deterministic orchestrator and LLM tests
│   └── tests/                    # Backend API and database test suite
├── frontend/                     # [Planned] React/Vite web application
├── orchestrator/                 # [Phase 10 — Next] AI agent orchestrator package
├── infra/                        # [Planned] Terraform & cloud infrastructure
└── README.md                     # Project documentation
```

---

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
* **Thin API Handlers**: Routers do not contain SQL queries or complex business logic. They delegate directly to the service layer.
* **Autonomous Orchestrator Separation**: AI agent orchestration will reside in `orchestrator/`, completely decoupled from REST request-response cycles.
* **Non-Bypassable RLS**: All queries pass through `get_authenticated_db`, ensuring PostgreSQL policies enforce boundaries even in the event of an application defect.

---

# 7. Security Architecture

### Authentication
* **Supabase JWT Integration**: Authenticated endpoints validate bearer tokens using `app.core.security.verify_supabase_jwt`.
* **Mandatory Signature Verification**: HMAC (HS256) and asymmetric JWKS public keys are verified strictly. Unsigned tokens or mismatched issuers/audiences are immediately rejected with HTTP 401.
* **UUID-Anchored Consistency**: Users are mapped strictly by the JWT `sub` claim matching `public.users.id`. Mutable identifiers (e.g., email) are never used as primary keys.

### Authorization
* **Project Boundary**: `require_project_access` verifies the authenticated user owns the target project (or is an active superuser). Non-owners receive HTTP 403 Forbidden.
* **Active Status Guard**: Deactivated users (`is_active = False`) are blocked from all endpoints by `require_active_user` with HTTP 403 Forbidden.

### PostgreSQL Row Level Security (RLS)
* **Session Context Injection**: `get_authenticated_db` executes `SET LOCAL request.jwt.claim.sub = :uid` within the request transaction.
* **Database-Enforced Policy**: Tables (`projects`, `incidents`, `investigations`, `repositories`, `user_github_connections`, `audit_logs`) enforce RLS policies via `public.has_project_access(project_id)`.
* **Zero Cross-User Leaks**: User A cannot read, insert, update, or delete User B's rows at the database engine level.

### Anti-Spoofing & Immutability
* **Authoritative URL Routing**: Resource ownership is determined by path parameters (`/projects/{project_id}/...`). Body-level `project_id` or `incident_id` injection is rejected.
* **Strict Schema Validation**: All write schemas use Pydantic `extra="forbid"`. Attempting to supply `id`, `project_id`, `created_at`, or `updated_at` returns HTTP 422 Unprocessable Entity.
* **Hierarchical Boundary Validation**: Every investigation request verifies that `incident_id` belongs to `project_id`, and that `investigation_id` belongs to `incident_id`.

### Secret Sanitization & Audit Logging
* **Zero Credential Exposure**: JWTs, GitHub access tokens, and OAuth secrets are never logged or returned in API responses.
* **Structured Audit Metadata**: Audit logs record timestamps, actor IDs, project IDs, incident IDs, investigation IDs, and status transition outcomes.

---

# 8. Database & Migrations

Database migrations are managed using Alembic. Historical migrations remain immutable:

| Migration | Revision | Description |
|---|---|---|
| `0001_initial_schema.py` | `0001_initial_schema` | Core schema: users, projects, repositories, incidents, investigations, evidence, fix proposals, approvals, audit logs |
| `0002_row_level_security.py` | `0002_row_level_security` | PostgreSQL Row Level Security policies, helper functions (`has_project_access`), table locks |
| `0003_github_connections.py` | `0003_github_connections` | GitHub OAuth connection table (`user_github_connections`) with RLS |
| `0004_incident_management.py` | `0004_incident_management` | Incident `source` enum, `detected_at` timestamps, composite query indexes |
| `0005_investigation_api.py` | `0005_investigation_api` | Investigation `summary`, `started_at` timestamps, query indexes; cleans speculative AI fields |

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

# 9. API Overview

All API endpoints are versioned under `/api/v1`:

| Domain | Method | Endpoint | Description | Auth Required |
|---|---|---|---|---|
| **Health** | `GET` | `/api/v1/health` | Liveness health check | Public |
| **Health** | `GET` | `/api/v1/ready` | Database readiness check | Public |
| **Auth** | `POST` | `/api/v1/auth/sync` | Provision or synchronize user profile from JWT | Bearer JWT |
| **Users** | `GET` | `/api/v1/users/me` | Retrieve authenticated user profile | Bearer JWT |
| **Users** | `PATCH` | `/api/v1/users/me` | Update mutable user profile fields | Bearer JWT |
| **Users** | `DELETE` | `/api/v1/users/me` | Deactivate account (soft delete) | Bearer JWT |
| **Projects** | `POST` | `/api/v1/projects` | Create a new project | Bearer JWT |
| **Projects** | `GET` | `/api/v1/projects` | List projects owned by authenticated user | Bearer JWT |
| **Projects** | `GET` | `/api/v1/projects/{project_id}` | Retrieve project by ID | Bearer JWT + Owner |
| **Projects** | `PATCH` | `/api/v1/projects/{project_id}` | Update project metadata | Bearer JWT + Owner |
| **Projects** | `DELETE` | `/api/v1/projects/{project_id}` | Delete project (cascades resources) | Bearer JWT + Owner |
| **GitHub** | `GET` | `/api/v1/github/connect` | Initiate OAuth flow with signed CSRF state | Bearer JWT |
| **GitHub** | `GET` | `/api/v1/github/callback` | OAuth redirect callback | Public (State-bound) |
| **GitHub** | `GET` | `/api/v1/github/connection` | Check connection status (tokens masked) | Bearer JWT |
| **GitHub** | `DELETE` | `/api/v1/github/connection` | Disconnect GitHub account | Bearer JWT |
| **GitHub** | `GET` | `/api/v1/github/repositories` | List accessible repositories | Bearer JWT |
| **GitHub** | `POST` | `/api/v1/projects/{project_id}/github/repository` | Attach GitHub repo to project | Bearer JWT + Owner |
| **GitHub** | `GET` | `/api/v1/projects/{project_id}/github/repository` | Get attached repository metadata | Bearer JWT + Owner |
| **GitHub** | `DELETE` | `/api/v1/projects/{project_id}/github/repository` | Disconnect repository from project | Bearer JWT + Owner |
| **GitHub** | `GET` | `/api/v1/projects/{project_id}/github/branches` | List repository branches | Bearer JWT + Owner |
| **GitHub** | `GET` | `/api/v1/projects/{project_id}/github/commits` | List recent commits | Bearer JWT + Owner |
| **GitHub** | `GET` | `/api/v1/projects/{project_id}/github/pulls` | List pull requests | Bearer JWT + Owner |
| **GitHub** | `GET` | `/api/v1/projects/{project_id}/github/issues` | List repository issues | Bearer JWT + Owner |
| **GitHub** | `GET` | `/api/v1/projects/{project_id}/github/contents` | Inspect file/directory contents | Bearer JWT + Owner |
| **GitHub** | `GET` | `/api/v1/projects/{project_id}/github/workflows` | List GitHub Actions workflow runs | Bearer JWT + Owner |
| **Incidents** | `POST` | `/api/v1/projects/{project_id}/incidents` | Create an incident | Bearer JWT + Owner |
| **Incidents** | `GET` | `/api/v1/projects/{project_id}/incidents` | List project incidents (paginated/filtered) | Bearer JWT + Owner |
| **Incidents** | `GET` | `/api/v1/projects/{project_id}/incidents/{incident_id}` | Retrieve incident details | Bearer JWT + Owner |
| **Incidents** | `PATCH` | `/api/v1/projects/{project_id}/incidents/{incident_id}` | Update mutable incident fields | Bearer JWT + Owner |
| **Incidents** | `PATCH` | `/api/v1/projects/{project_id}/incidents/{incident_id}/status` | Dedicated lifecycle status transition | Bearer JWT + Owner |
| **Incidents** | `DELETE` | `/api/v1/projects/{project_id}/incidents/{incident_id}` | Delete incident | Bearer JWT + Owner |
| **Investigations** | `POST` | `/api/v1/projects/{project_id}/incidents/{incident_id}/investigations` | Create an investigation | Bearer JWT + Owner |
| **Investigations** | `GET` | `/api/v1/projects/{project_id}/incidents/{incident_id}/investigations` | List investigations for incident | Bearer JWT + Owner |
| **Investigations** | `GET` | `/api/v1/projects/{project_id}/incidents/{incident_id}/investigations/{id}` | Retrieve investigation details | Bearer JWT + Owner |
| **Investigations** | `PATCH` | `/api/v1/projects/{project_id}/incidents/{incident_id}/investigations/{id}` | Update mutable fields | Bearer JWT + Owner |
| **Investigations** | `PATCH` | `/api/v1/projects/{project_id}/incidents/{incident_id}/investigations/{id}/status` | Transition lifecycle status | Bearer JWT + Owner |
| **Investigations** | `DELETE` | `/api/v1/projects/{project_id}/incidents/{incident_id}/investigations/{id}` | Delete investigation | Bearer JWT + Owner |

---

# 10. Implemented Backend Phases

### Phase 5 — Authentication & Authorization
* Validates Supabase JWTs cryptographically; enforces user mapping to verified `sub` claims.
* Provides authenticated database sessions via `get_authenticated_db` to propagate session context to PostgreSQL RLS.

### Phase 6 — User & Project APIs
* Implements profile management (`/users/me`) and project CRUD (`/projects`).
* Prevents spoofing via `extra="forbid"`, automatically anchors `owner_id`, and cascades deletion to child resources.

### Phase 7 — GitHub Integration
* Implements secure GitHub OAuth connection with signed HMAC CSRF state.
* Provides project repository attachment and inspection endpoints (branches, commits, PRs, issues, files, workflows).
* Enforces strict credential masking (access tokens are never logged or returned in responses).

### Phase 8 — Incident Management
* Implements operational incident lifecycle: `OPEN` → `INVESTIGATING` → `MITIGATED` → `RESOLVED` → `CLOSED`.
* Provides bounded pagination (max 100), deterministic sorting (`created_at DESC`), and filtering by status, severity, and source.

### Phase 9 — Investigation API
* Implements the investigation API data contract and finite state machine.
* Enforces active-investigation concurrency limits (HTTP 409 if a run is already active).
* Validates dual project and incident boundaries, tracks execution timestamps (`started_at`, `completed_at`), and prepares token/cost tracking for Phase 13.

---

# 11. Phase 7 — GitHub Integration

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

* **Anti-SSRF & Input Validation**: All repository requests go through typed client methods with strict owner/repository format validation. Path traversal (`..`) in contents queries is rejected.
* **Rate Limit Handling**: GitHub API rate limits (HTTP 429) and upstream errors are caught and transformed into structured application error responses.

---

# 12. Phase 8 — Incident Management

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

* **Controlled Transitions**: Validated in `IncidentService.validate_status_transition`. Arbitrary jumps (e.g., `OPEN` → `CLOSED`) raise HTTP 422.
* **Controlled Enums**:
  * Severity: `low`, `medium`, `high`, `critical`, `info`
  * Source: `manual`, `github`, `monitoring`, `webhook`, `system`
* **Automated Bookkeeping**: `resolved_at` is automatically recorded when transitioning into `RESOLVED` or `CLOSED`, and cleared if reopened.

---

# 13. Phase 9 — Investigation API

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

* **Allowed Transitions**:
  * `PENDING` → `RUNNING`, `CANCELLED`
  * `RUNNING` → `COMPLETED`, `FAILED`, `CANCELLED`
  * `COMPLETED`, `FAILED`, `CANCELLED` are terminal states (idempotent same-state updates allowed).
  * Invalid transitions raise HTTP 422 Unprocessable Entity.
* **Active-Investigation Concurrency Rule**: Only **one** active investigation (`PENDING` or `RUNNING`) can exist per incident at any time. Attempting to create a second concurrent active investigation returns HTTP 409 Conflict. Once completed, failed, or cancelled, subsequent investigations can be created.
* **Timestamp & Lifecycle Tracking**:
  * `started_at` is automatically populated when entering `RUNNING`.
  * `completed_at` is automatically populated when entering `COMPLETED`, `FAILED`, or `CANCELLED`.
  * `error_message` records failure reasons when transitioning to `FAILED`.
* **Token & Cost Budgeting Foundation**:
  * `tokens_used`: Integer tracking tokens consumed (defaults to `0`, non-negative constraint).
  * `estimated_cost_usd`: Integer tracking cost in micro-USD (defaults to `0`, non-negative constraint).
* **Architectural Boundaries**:
  * Speculative AI/result fields (`root_cause_summary`, `confidence_score`) were intentionally excluded from Phase 9. AI diagnostic synthesis belongs to Phase 15.

---

# 14. Investigation Pipeline: Phases 10+

> **Status: Phases 10–15 implemented; Phases 16+ planned**

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
  Produces code patch diffs, config adjustments, or rollback commands
       │
       ▼
Sandbox Verification [Phase 17]
  Executes candidate fix in an isolated Docker container to verify test pass
       │
       ▼
Human Approval Gate [Phase 18]
  Interactive human-in-the-loop review of diagnosis, evidence, and proposed fix
       │
       ▼
Production Resolution [Phase 18]
  Fix applied via Pull Request or deployment rollback; incident marked RESOLVED
```

---

# 15. AI Reasoning and Knowledge Search

> **Status: Implemented — Phase 13 (opt-in; no model call at startup or in tests)**

## Phase 13 — NVIDIA / Nebius Reasoning and Cost Control

Phase 13 consumes the normalized Phase 12 evidence collection and returns structured observations, explicit uncertainties, and follow-up questions. Its output is evidence-referenced and is not a root-cause diagnosis or a fix proposal.

* **Provider boundary**: `LLMProvider` separates provider-neutral orchestration from the Nebius OpenAI-compatible Nemotron adapter. A deterministic fake provider is used in automated tests.
* **Explicit opt-in**: `LLM_ENABLED=false` by default. No model client is constructed, and no outbound LLM call occurs during imports, application startup, health checks, local tests, or CI. To use the provider, explicitly construct it with `create_nebius_llm_service(settings)` and inject that service into `DEVDOCOrchestrator` or an operational stage registry.
* **Budget cap**: Each outbound attempt first reserves its worst-case input/output cost against a maximum configured budget of $25. The factory uses an atomic SQLite ledger (default `backend/.devdoc-llm-budget.sqlite3`) so spend and in-flight reservations survive restarts and are shared by processes using the same local filesystem. Failed or crash-interrupted attempts consume their reservation because provider-side billing may be unknown. SQLite does not coordinate separate hosts; multi-host live inference requires a shared transactional budget store, which is outside this phase.
* **Pricing configuration**: Set both `LLM_INPUT_COST_PER_MILLION_USD` and `LLM_OUTPUT_COST_PER_MILLION_USD` to the current price for the configured Nebius model before enabling requests. Zero/unset rates cause service construction to fail closed; estimates are not a provider invoice.
* **Token and request bounds**: UTF-8 request size is conservatively bounded by the configured input-token limit; output tokens, HTTP timeout, retries (maximum three), and exponential backoff are also capped.
* **Cache**: Successful structured results are kept in a bounded in-memory TTL cache. Cache hits make no provider request and have zero additional token cost.
* **Response safety**: Provider JSON is validated against strict Pydantic contracts. Every referenced evidence ID must belong to the submitted evidence set. Evidence text is sanitized and treated as untrusted data.
* **Observability**: Results include provider/model, request ID, duration, attempts, input/output token counts, estimated spend, budget remaining, and cache-hit status. Prompts and credentials are excluded.
* **Secret handling**: The Nebius API key is a `SecretStr`, sent only in the server-side HTTPS Authorization header, and never included in logs or error messages.

See `backend/.env.example` for the complete Phase 13 configuration. Do not enable live inference without setting current Nebius token prices and explicitly injecting the configured service.

## Phase 14 — Knowledge Search / Tavily

> **Status: Implemented — opt-in; automated tests use fake providers or HTTPX mock transports**

Phase 14 adds a provider-neutral search service with a Tavily adapter. `AnalyzeStage` can search after evidence collection and before the optional LLM reasoning call. Search is only available when a `KnowledgeSearchService` is explicitly constructed and injected; the default application workflow does not construct it or make search calls.

* **Bounded query and results**: Queries are built from allow-listed investigation/evidence fields, sanitized, and length-limited. Search depth, result count, response size, title/content/URL lengths, timeout, retries, concurrency, per-investigation usage, and cache capacity are configurable and validated.
* **Safe provider boundary**: The adapter calls Tavily over HTTPS, keeps `TAVILY_API_KEY` server-side, requests neither generated answers nor raw page content, and never follows result URLs. Returned URLs are accepted only after HTTPS and host validation; private/local destinations and non-allow-listed domains (when configured) are rejected.
* **Evidence provenance and trust**: Search results are normalized and merged through the Phase 12 Evidence Engine with provider, query, URL, retrieval timestamp, and an `untrusted_external` classification. These references are not observed incident facts. The Phase 13 reasoning prompt explicitly treats page text as untrusted and preserves source links.
* **Failure behavior**: A search failure preserves collected evidence, marks analysis as failed, and skips LLM reasoning for that stage. The orchestrator's existing `FAIL_FAST` or `CONTINUE_ON_FAILURE` workflow policy controls downstream stages.
* **Caching and process-local limits**: A bounded TTL cache is scoped to project, investigation, execution, and query. Usage limits and concurrency controls are held in memory per service instance; they are not durable or shared across hosts.
* **Phase boundary**: This phase retrieves and attributes references only. It does not diagnose root cause, generate fixes, fetch arbitrary pages, run commands, verify changes, or perform remediation.

Search remains disabled unless `KNOWLEDGE_SEARCH_ENABLED=true`, a server-side `TAVILY_API_KEY` is configured, and the service is explicitly injected. See `backend/.env.example` for the bounded controls. Phase 14 tests use fake providers and `httpx.MockTransport`; no automated test or startup path makes a live Tavily or Nebius request.

## Phase 15 — Root Cause Analysis Engine

> **Status: Implemented — analysis-only; Nemotron remains opt-in**

Phase 15 evaluates ranked incident-specific hypotheses from the Phase 12 evidence collection, Phase 13 reasoning (when available), Phase 14 external references, and the existing timeline/correlation graph. It is integrated into `DiagnoseStage` through an explicitly injected `RootCauseAnalysisService`; the default application does not construct an LLM or make inference calls.

* **Evidence-grounded contract**: The output separates recorded `FACT` evidence references from `EXTERNAL_KNOWLEDGE`. Every candidate is explicitly classified as a `HYPOTHESIS` and must cite at least one actual observed evidence ID. Summary and hypothesis-chain claims require valid evidence references; unknown or fabricated evidence and correlation IDs fail validation.
* **Hypothesis chain**: Candidates may describe contributing factors, triggering events, and observed symptoms separately. Phase 12 timeline and correlation IDs are provided as context; temporal order and correlation are not treated as causation.
* **Contradictions and uncertainty**: Candidates include supporting and contradicting evidence plus uncertainties. Deterministic ranking uses unique observed evidence items, independent evidence sources, and observed contradictions; repeated IDs cannot inflate evidence strength. A tie among plausible candidates is returned as `multiple_plausible_causes`.
* **Confidence and selection**: `LOW` means evidence is sparse, dependent, or contradicted; `MEDIUM` means at least two unique observations from two sources support the candidate and contradictions are fewer than supports; `HIGH` requires at least three unique observations from two sources and no observed contradiction. These are qualitative evidence tiers, not probabilities. Only a uniquely strongest `HIGH` candidate is selected; a weaker or tied result remains unselected.
* **Missing information**: The result identifies discriminating evidence to collect next. With no evidence, the stage returns `insufficient_evidence` without an LLM call.
* **Prompt and output safety**: Evidence, logs, model reasoning, and external content are delimited as untrusted data. The prompt forbids following embedded instructions, inventing facts/IDs/URLs/timestamps, or proposing fixes. Strict Pydantic validation checks schema, category enums, evidence IDs, temporal relationship IDs, and generated URLs before accepting output.
* **LLM, budgets, and cache**: RCA uses `LLMService.complete_structured`, reusing Phase 13's provider, global budget guard, token bounds, retry/timeout controls, safe observability, and bounded in-memory cache. Cache keys include project, investigation, execution, model, and the full sanitized prompt. An in-memory per-service limit allows at most three RCA analyses per project/investigation; usage limits are not shared across hosts.
* **Failure and cancellation**: Budget, provider, timeout, schema, and reference failures are surfaced as a failed diagnosis stage and follow the configured orchestrator failure policy. Cancellation is checked before requests and retries; if requested while a provider call is in flight, the active request may complete, but no further retry is started and the result is not accepted.
* **No persistence or actions**: Analysis is returned in the orchestration stage result; it does not mutate evidence or add database tables/migrations. There is no public RCA endpoint. Phase 15 does not generate patches, commands, or fixes, execute operations, modify production or GitHub, or bypass approval.

All Phase 15 automated tests use a fake provider. There is no real-model smoke test enabled by default; a real request occurs only when an operator explicitly constructs and injects the configured Nebius service, and it consumes the existing Phase 13 budget.

---

# 16. Local Development

### Prerequisites
* Python 3.13 or higher
* Docker (for local PostgreSQL / Supabase testing)
* Git

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

# 17. Testing & Quality

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

> **Verification Snapshot (Phase 11 Completion)**:
> * Full Test Suite: **288 passed, 14 skipped, 0 failed** (100% pass rate across 302 tests).
> * Phase 11 Operational Agent Tests: **38 passed, 0 failed** (100% pass rate).
> * Phase 10 Orchestrator Tests: **55 passed, 0 failed** (100% pass rate).
> * Ruff Lint Check: **All checks passed!** (0 errors, 0 warnings).
> * Mypy Analysis: **Clean across all Phase 11 and Orchestrator modules**.

---

# 18. Docker

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
```

---

# 19. Team & Ownership

DEVDOC is built and maintained by a 5-member engineering team:

| Member | Role | Primary Responsibilities |
|---|---|---|
| **Member 1** | Backend / API | FastAPI endpoints, routing, schemas, API versioning, business services |
| **Member 2** | Database / Auth | PostgreSQL schema, SQLAlchemy models, Supabase RLS, JWT authentication |
| **Member 3** | AI / Agent | Orchestrator package, evidence collection, Nemotron/Nebius reasoning, root cause engine |
| **Member 4** | DevOps / Integrations / Sandbox | GitHub OAuth, containerization, Docker sandbox verification, CI/CD pipelines |
| **Member 5** | Security / QA / Operations | Security audit, vulnerability review, load testing, telemetry, test coverage |

---

# 20. Git Workflow

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

* `prd`: Production-ready code. Merges occur only from `dev` after full release validation.
* `dev`: Active development integration. Merges occur from `features` after integration sign-off.
* `features`: Approved phase integration baseline. Completed phase branches PR into `features`.
* `feature/*`: Scoped branches for individual development phases (e.g., `feature/phase9-investigation-api`).

---

# 21. Development Rules

1. **Strict Branch Scoping**: Each pull request must address exactly one development phase or feature. Unrelated modifications are prohibited.
2. **Mandatory Quality Gates**: Every branch must pass `python -m ruff check .` and the complete `python -m pytest -v` regression suite before PR creation.
3. **No Secret Commits**: Never commit `.env` files, API keys, private tokens, or credentials. Use `.env.example` placeholders.
4. **Thin API Routing**: Business logic must reside in `app/services/`, not inside FastAPI route handlers.
5. **Defense in Depth**: Always enforce authorization at the application layer (`dependencies.py`) and verify database-level isolation via PostgreSQL RLS.

---

# 22. Environment Variables

Configure `.env` locally using `backend/.env.example` as a template:

| Variable | Description | Example / Default |
|---|---|---|
| `ENVIRONMENT` | Deployment environment | `development`, `staging`, `production` |
| `DATABASE_URL` | Async PostgreSQL connection string | `postgresql+asyncpg://postgres:postgres@localhost:5432/devdoc` |
| `DIRECT_DATABASE_URL` | Direct connection for Alembic migrations | `postgresql+asyncpg://postgres:postgres@localhost:5432/devdoc` |
| `SUPABASE_URL` | Supabase project URL | `https://your-project.supabase.co` |
| `SUPABASE_JWT_SECRET` | Secret key for JWT verification | `minimum-32-characters-secret-key` |
| `SUPABASE_JWT_ALGORITHM` | JWT signing algorithm | `HS256` |
| `SUPABASE_JWT_AUDIENCE` | Expected JWT audience | `authenticated` |
| `SUPABASE_JWT_ISSUER` | Expected JWT issuer | `https://your-project.supabase.co/auth/v1` |
| `GITHUB_CLIENT_ID` | GitHub OAuth application client ID | `your-github-client-id` |
| `GITHUB_CLIENT_SECRET` | GitHub OAuth application client secret | `your-github-client-secret` |
| `GITHUB_OAUTH_REDIRECT_URI` | GitHub OAuth callback redirect URI | `http://localhost:8000/api/v1/github/callback` |
| `GITHUB_API_BASE_URL` | GitHub API base URL | `https://api.github.com` |
| `LLM_ENABLED` | Enable live Phase 13 reasoning; defaults to disabled | `false` |
| `NEBIUS_API_KEY` | Server-side Nebius token API key | Leave empty until explicitly enabling |
| `NEBIUS_BASE_URL` | Nebius OpenAI-compatible API base URL | `https://api.studio.nebius.ai/v1` |
| `NEBIUS_MODEL` | Nemotron model identifier | `nvidia/Llama-3.1-Nemotron-70B-Instruct` |
| `LLM_TIMEOUT_SECONDS` | Per-request HTTP timeout (maximum 120 seconds) | `30` |
| `LLM_MAX_ATTEMPTS` | Maximum attempts per request (maximum 3) | `2` |
| `LLM_MAX_INPUT_TOKENS` | Maximum conservative input-size budget | `12000` |
| `LLM_MAX_OUTPUT_TOKENS` | Provider output-token ceiling | `1000` |
| `LLM_BUDGET_USD` | Process guard ceiling; cannot exceed project credit budget | `25` |
| `LLM_BUDGET_LEDGER_PATH` | Persistent SQLite spend/reservation ledger path | `.devdoc-llm-budget.sqlite3` |
| `LLM_INPUT_COST_PER_MILLION_USD` | Current Nebius input price for configured model | `0` (must be configured to enable) |
| `LLM_OUTPUT_COST_PER_MILLION_USD` | Current Nebius output price for configured model | `0` (must be configured to enable) |
| `LLM_CACHE_TTL_SECONDS` | Successful-result in-memory cache TTL | `900` |
| `LLM_CACHE_MAX_ENTRIES` | Maximum successful-result cache entries | `128` |
| `KNOWLEDGE_SEARCH_ENABLED` | Enable explicit Phase 14 knowledge-search service construction | `false` |
| `TAVILY_API_KEY` | Server-side Tavily API key; leave empty unless search is explicitly enabled | *(empty)* |
| `KNOWLEDGE_SEARCH_TIMEOUT_SECONDS` | Maximum Tavily request timeout | `8` |
| `KNOWLEDGE_SEARCH_MAX_RESULTS` | Maximum results per search | `5` |
| `KNOWLEDGE_SEARCH_MAX_QUERY_LENGTH` | Maximum sanitized search-query length | `400` |
| `KNOWLEDGE_SEARCH_MAX_RESPONSE_BYTES` | Maximum response size accepted | `250000` |
| `KNOWLEDGE_SEARCH_MAX_RETRIES` | Bounded retry count | `1` |
| `KNOWLEDGE_SEARCH_DEPTH` | Tavily search depth | `basic` |
| `KNOWLEDGE_SEARCH_PREFERRED_DOMAINS` | Comma-separated preferred bare domains | *(empty)* |
| `KNOWLEDGE_SEARCH_ALLOWED_DOMAINS` | Optional strict comma-separated result-domain allow-list | *(empty)* |
| `KNOWLEDGE_SEARCHES_PER_INVESTIGATION` | Maximum provider attempts per investigation window | `2` |
| `KNOWLEDGE_SEARCH_MAX_CONCURRENT` | Maximum in-flight provider calls per service instance | `2` |
| `KNOWLEDGE_SEARCH_CACHE_TTL_SECONDS` | Successful-result cache lifetime | `600` |
| `KNOWLEDGE_SEARCH_CACHE_MAX_ENTRIES` | Maximum cached results | `128` |

---

# 23. Current Limitations & Phase Status

As of Phase 14 completion, the orchestration framework, operational investigation agents, bounded evidence processing pipeline, and opt-in LLM reasoning and knowledge-search layers are established:

### IMPLEMENTED (Phase 10 — DEVDOC Orchestrator)
* **Orchestration Engine**: Central DEVDOCOrchestrator coordinating sequential stage execution, failure handling, and execution tracing (ackend/orchestrator/core/orchestrator.py).
* **Investigation Context**: Strongly typed InvestigationContext with UUID validation, timestamping, audit logs, and strict credential/secret prevention (ackend/orchestrator/core/context.py).
* **Stage Model**: Canonical 7-stage lifecycle contracts (INITIALIZE → COLLECT → ANALYZE → DIAGNOSE → PROPOSE → VERIFY → COMPLETE) (ackend/orchestrator/contracts/stage.py, ackend/orchestrator/stages/investigation.py).
* **Agent Abstraction & Mock Agent**: Standardized BaseAgent contract and deterministic MockInvestigationAgent with zero external network or AI token calls (ackend/orchestrator/contracts/agent.py, ackend/orchestrator/agents/base.py).
* **Workflow Definition & Failure Policy**: WorkflowDefinition supporting deterministic FAIL_FAST halting of downstream stages upon critical errors (ackend/orchestrator/contracts/execution.py).
* **Stage Registry**: Injected StageRegistry providing stage lookup, registration, duplicate detection, and deterministic ordering (ackend/orchestrator/stages/registry.py).
* **InvestigationService Integration**: Clean service-boundary integration methods uild_orchestration_context and 
un_investigation_orchestration in ackend/app/services/investigation.py.

### IMPLEMENTED (Phase 11 — Operational Investigation Agents)
* **GitHub Agent (GitHubAgent)**: Structured inspection of repository metadata, branches, recent commits, pull requests, issues, bounded file contents, and GitHub Actions workflow runs. Reuses existing Phase 7 GitHubAPIClient without duplicating auth or exposing tokens (ackend/orchestrator/agents/github_agent.py).
* **Docker Agent (DockerAgent)**: Structured inspection of container status, exit codes, OOMKilled flags, restart counts, image tags, and bounded log streams via DockerInspector abstraction (DockerHTTPInspector, FakeDockerInspector). Strictly prohibits arbitrary shell execution, os.system, and subprocess (ackend/orchestrator/agents/docker_agent.py, ackend/orchestrator/agents/docker_inspector.py).
* **Monitoring Agent (MonitoringAgent)**: Vendor-neutral monitoring inspection via MonitoringProvider abstraction (GenericHTTPMonitoringProvider, FakeMonitoringProvider). Gathers service health, CPU/memory metrics, latency percentiles, error rates, and firing alerts. Enforces anti-SSRF protection against AWS/GCP/Azure link-local metadata endpoints (ackend/orchestrator/agents/monitoring_agent.py, ackend/orchestrator/agents/monitoring_provider.py).
* **Operational Data Sanitizer**: Recursive sanitization of sensitive dictionary keys and regex-based redaction of personal access tokens, OAuth tokens, Bearer headers, private keys, and passwords (ackend/orchestrator/core/sanitizer.py).
* **Typed Agent Results**: Extended AgentResult contract with investigation_id, execution_id, source, data, warnings, errors, and collected_at (100% backward compatible with Phase 10).
* **Orchestrator Stage Integration**: CollectEvidenceStage dynamically executes all injected operational agents, propagating sanitized data and recording typed results into InvestigationContext (ackend/orchestrator/stages/investigation.py).

### IMPLEMENTED (Phase 12 — Evidence Engine)
* **Multi-modal normalization**: Converts GitHub repository/commit/PR/issue/workflow/file results, Docker container/state/log results, monitoring health/metric/alert results, and generic agent payloads into typed evidence records.
* **Data integrity and safety**: Normalizes timestamps to UTC, records timestamp provenance, sanitizes secrets in payload and display text, validates identifiers and payload size, bounds nested input, and records quality warnings.
* **Deduplication and summaries**: Applies stable provider identifiers or canonical content hashes and summarizes counts, time bounds, duplicate counts, data-quality failures, and source/type groups.
* **Timeline and evidence graph**: Produces a stable chronological timeline and explicit shared-identifier / temporal-proximity edges. Correlation links are informational and do not imply causality.
* **Orchestrator integration**: `CollectEvidenceStage` processes agent results and returns the bounded serialized evidence collection alongside collection summary counts.
* **Resource guardrails**: Configurable limits cap agent/evidence count, per-item and aggregate payload bytes, field length, source records, timeline entries, graph edges, and correlation windows.

### IMPLEMENTED (Phase 13 — Nemotron / Nebius Reasoning)
* **Provider abstraction and Nebius adapter**: Async provider contract and HTTPS-only OpenAI-compatible Nemotron client; API key remains server-side.
* **Structured reasoning contract**: Sanitized evidence-set input, strict Pydantic output validation, evidence-ID validation, and explicit boundary against root-cause claims and fix generation.
* **Token, cost, and budget controls**: Input/output limits, configurable price-based estimates, pre-request worst-case reservations, a hard `$25` maximum, and bounded retry/timeouts.
* **Cache and observability**: Bounded TTL cache plus safe request, usage, duration, and estimated cost metadata.
* **Orchestrator integration**: `AnalyzeStage` receives the collected evidence and calls the provider only when an `LLMService` is explicitly injected. The default workflow remains offline.
* **Deterministic tests**: All LLM service tests use fake providers or `httpx.MockTransport`; no automated test makes live model calls.

### IMPLEMENTED (Phase 14 — Knowledge Search / Tavily)
* **Provider abstraction and Tavily adapter**: Async provider protocol, deterministic fake provider, HTTPS Tavily client, explicit secret handling, bounded response streaming, and no automatic result-URL fetching.
* **Query and result safety**: Sanitized, bounded query construction; HTTPS/public-host and optional domain allow-list validation; response and field-size limits; retry, timeout, concurrency, usage, and cache controls.
* **Evidence integration and provenance**: Normalizes external references through the Phase 12 Evidence Engine and stores URL, provider, query, retrieval time, and untrusted-source classification.
* **Orchestrator integration**: Optional injected search runs before the optional Phase 13 reasoning call. Search failures preserve existing evidence and are governed by the workflow failure policy.
* **Deterministic tests**: Fake providers and HTTPX mock transports; no live search/model calls in automated tests, imports, or startup.

### IMPLEMENTED (Phase 15 — Root Cause Analysis Engine)
* **Evidence-referenced analysis**: Strict typed RCA contracts distinguish observed facts, untrusted external knowledge, and hypotheses; candidate claims must cite actual Phase 12 evidence IDs.
* **Hypothesis evaluation**: Ranks candidate causes with deterministic qualitative confidence based on unique observed references, independent sources, and contradictions. Only a uniquely strongest high-confidence hypothesis can be selected; ties and weak evidence remain unselected.
* **Temporal and external context**: Reuses Phase 12 timeline/correlation relationships and Phase 14 source URLs. It treats temporal order as correlation rather than proof and external documentation as interpretation rather than incident fact.
* **LLM safety and integration**: Injected RCA service uses the Phase 13 provider, global budget guard, bounded tokens/retries, and TTL cache. Prompt data is delimited as untrusted; schema, evidence references, and relationship references are validated before output.
* **Analysis-only behavior**: The Diagnose stage exposes the structured result in orchestration output. There is no RCA database migration or public endpoint, and Phase 15 generates no fixes or production actions.
* **Deterministic tests**: Phase 15 coverage uses fake LLM providers; normal tests make no Nebius/Tavily calls.

### NOT IMPLEMENTED (Planned for Phase 16+)
* **Fix Generator**: Automated code patch and configuration generation (Phase 16).
* **Sandbox Verification**: Isolated containerized verification of proposed fixes (Phase 17).
* **Human Approval & Audit**: Approval gates and production remediation (Phase 18+).

---

# 24. License

Proprietary / Internal project license. All rights reserved. DEVDOC Team.
