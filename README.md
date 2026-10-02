# DEVDOC

**DEVDOC** is an AI-powered DevOps and SRE incident investigation and remediation platform. It provides development and operations teams with an automated, evidence-grounded pipeline to investigate operational outages, analyze system telemetry, diagnose root causes, and generate verified fixes with human-in-the-loop approval.

> **Current Status**: Phase 1–10 backend foundation and orchestrator complete. AI Agents (Phase 11+) upcoming.

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

* **Implemented Today (Phases 1–10)**: Production-grade backend foundation, Supabase database models, Row Level Security (RLS) policies, JWT authentication, user and project management, GitHub OAuth and repository inspection, incident management, investigation API contract, and the foundational AI Investigation Orchestrator (`backend/orchestrator`).
* **Planned (Phase 11+)**: Dedicated GitHub/Docker/Monitoring investigation agents, multi-modal evidence collection, Nemotron/Nebius LLM reasoning, Tavily web search, automated root cause synthesis, sandbox fix verification, and interactive human-in-the-loop approval gates.


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
  GitHub Agent   Docker Agent   Telemetry Agent  [Phase 11 — Planned]
       │               │               │
       └───────────────┬───────────────┘
                       ▼
                Evidence Engine            [Phase 12 — Planned]
                       │
                       ▼
         NVIDIA Nemotron via Nebius        [Phase 13 — Planned]
                       │
                       ▼
            Tavily Knowledge Search        [Phase 14 — Planned]
                       │
                       ▼
               Root Cause Engine           [Phase 15 — Planned]
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

### Planned Future Technologies (Phases 10+)

| Component | Planned Technology | Target Phase |
|---|---|---|
| AI Reasoning Model | NVIDIA Nemotron 70B via Nebius Token API | Phase 13 |
| Knowledge Search | Tavily API | Phase 14 |
| Agent Orchestration | DEVDOC Custom Orchestrator Package | Phase 10 |
| Sandbox Execution | Isolated Docker / MicroVM Environments | Phase 17 |
| Real-Time Observability | OpenTelemetry + Prometheus / Grafana | Phase 21 |

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
| 10 | 🔵 Next | DEVDOC Orchestrator | Autonomous agent orchestrator package, workflow coordination |
| 11 | ⏳ Planned | Investigation Agents | Specialized GitHub, Docker, and Monitoring inspection agents |
| 12 | ⏳ Planned | Evidence Engine | Structured evidence collection, normalization, and timeline assembly |
| 13 | ⏳ Planned | NVIDIA Nemotron + Nebius | LLM client integration, budget guardrails, token/cost optimization |
| 14 | ⏳ Planned | Knowledge Search / Tavily | External documentation, CVE, and error solution retrieval |
| 15 | ⏳ Planned | Root Cause Engine | Causal analysis, diagnostic synthesis, hypothesis ranking |
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
│   └── tests/                    # Comprehensive test suite (Phases 1–9)
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

# 14. Future AI Investigation Pipeline

> **Status: Planned — Phase 10+**

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

# 15. NVIDIA / Nebius Cost Control

> **Status: Planned — Phase 13**

The Phase 13 AI integration will implement strict cost and token guardrails:
* **Budget Guards**: Pre-run checks against project-level monthly token and expenditure quotas.
* **Token Tracking**: Per-investigation recording of `tokens_used` and `estimated_cost_usd` in micro-USD ($0.000001 precision).
* **Token Limits**: Hard caps on prompt context windows and max output tokens per model call.
* **Prompt Caching**: Deduplication of static system instructions and unchanged repository context.
* **Retry Limits & Circuit Breakers**: Bounded exponential backoff to avoid runaway billing on upstream model errors.
* **Zero Client Exposure**: AI provider API keys remain exclusively on the server and are never exposed to the client.

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

> **Verification Snapshot (Phase 9 Completion)**:
> * Full Test Suite: **208 passed, 1 skipped, 0 failed** (100% pass rate).
> * Ruff Lint Check: **All checks passed!** (0 errors, 0 warnings).

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
| `NEBIUS_API_KEY` | *(Planned Phase 13)* Nebius token API key | `nebius-api-key-placeholder` |
| `TAVILY_API_KEY` | *(Planned Phase 14)* Tavily search API key | `tavily-api-key-placeholder` 

---

# 23. Current Limitations & Phase Status

As of Phase 10 completion, the foundational orchestration framework is established:

### IMPLEMENTED (Phase 10 — DEVDOC Orchestrator)
* **Orchestration Engine**: Central DEVDOCOrchestrator coordinating sequential stage execution, failure handling, and execution tracing (ackend/orchestrator/core/orchestrator.py).
* **Investigation Context**: Strongly typed InvestigationContext with UUID validation, timestamping, audit logs, and strict credential/secret prevention (ackend/orchestrator/core/context.py).
* **Stage Model**: Canonical 7-stage lifecycle contracts (INITIALIZE → COLLECT → ANALYZE → DIAGNOSE → PROPOSE → VERIFY → COMPLETE) (ackend/orchestrator/contracts/stage.py, ackend/orchestrator/stages/investigation.py).
* **Agent Abstraction & Mock Agent**: Standardized BaseAgent contract and deterministic MockInvestigationAgent with zero external network or AI token calls (ackend/orchestrator/contracts/agent.py, ackend/orchestrator/agents/base.py).
* **Workflow Definition & Failure Policy**: WorkflowDefinition supporting deterministic FAIL_FAST halting of downstream stages upon critical errors (ackend/orchestrator/contracts/execution.py).
* **Stage Registry**: Injected StageRegistry providing stage lookup, registration, duplicate detection, and deterministic ordering (ackend/orchestrator/stages/registry.py).
* **InvestigationService Integration**: Clean service-boundary integration methods uild_orchestration_context and 
un_investigation_orchestration in ackend/app/services/investigation.py.

### NOT IMPLEMENTED (Planned for Future Phases)
* **Investigation Agents**: Dedicated GitHub, Docker, and Monitoring agents (Phase 11).
* **Evidence Engine**: Automated multi-modal evidence collection and timeline correlation (Phase 12).
* **Nemotron Reasoning via Nebius**: NVIDIA Nemotron LLM reasoning and token budget guarding (Phase 13).
* **Knowledge Retrieval**: Web search and external incident knowledge lookup via Tavily (Phase 14).
* **Root Cause Engine**: Automated causal graph synthesis and fault diagnosis (Phase 15).
* **Fix Generator**: Automated code patch and configuration generation (Phase 16).
* **Sandbox Verification**: Isolated containerized verification of proposed fixes (Phase 17).
* **Human Approval & Audit**: Approval gates and production remediation (Phase 18+).

---

# 24. License

Proprietary / Internal project license. All rights reserved. DEVDOC Team.
