# DEVDOC

**DEVDOC** is an AI-powered DevOps and SRE platform that helps development teams investigate application, infrastructure, and deployment problems — and propose verified fixes.

> ⚠️ **Phase 4 — Supabase Row Level Security (RLS) complete.** Phases 1–4 of the backend are implemented. Authentication (Phase 5) and Project/User APIs (Phase 6) are coming in subsequent phases.

---

## Backend — Phase 4 — Supabase Row Level Security (RLS)

### Technology Stack

| Layer | Technology |
|---|---|
| Language | Python 3.13+ |
| Framework | FastAPI |
| Server | Uvicorn |
| Validation | Pydantic v2 |
| Config | pydantic-settings |
| Testing | pytest + pytest-asyncio + HTTPX |
| Linting | Ruff |

---

### Prerequisites

- Python 3.13 or higher
- `pip` (bundled with Python)

---

### Setup

#### 1. Create and activate a virtual environment

```bash
# From the repository root
cd backend
python -m venv .venv

# Windows (PowerShell)
.venv\Scripts\Activate.ps1

# macOS / Linux
source .venv/bin/activate
```

#### 2. Copy the environment file

```bash
cp .env.example .env
```

Edit `.env` if you need to change any defaults. **Never commit `.env`.**

#### 3. Install runtime dependencies

```bash
pip install -r requirements.txt
```

#### 4. Install development dependencies

```bash
pip install -r requirements-dev.txt
```

---

### Running the API

```bash
cd backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

The server starts at: `http://localhost:8000`

---

### Health Endpoint

```
GET http://localhost:8000/api/v1/health
```

Expected response:

```json
{
    "success": true,
    "service": "DEVDOC",
    "status": "healthy"
}
```

---

### API Documentation

| URL | Description |
|---|---|
| `http://localhost:8000/docs` | Interactive Swagger UI |
| `http://localhost:8000/redoc` | ReDoc documentation |
| `http://localhost:8000/openapi.json` | Raw OpenAPI schema |

---

### Running Tests

```bash
cd backend
pytest
```

Run with verbose output:

```bash
pytest -v
```

---

### Linting with Ruff

Check for lint errors:

```bash
cd backend
ruff check .
```

Auto-fix safe issues:

```bash
ruff check . --fix
```

---

### Docker

Build the image:

```bash
cd backend
docker build -t devdoc-backend:phase1 .
```

Run the container:

```bash
docker run -p 8000:8000 devdoc-backend:phase1
```

---

---

### Database & Row Level Security (RLS) — Phase 4

Phase 4 implements defense-in-depth authorization directly inside PostgreSQL via Supabase Row Level Security (RLS). Database-level constraints ensure that authenticated users cannot access, modify, or inject records into projects they do not own.

#### Protected Tables (10 Tables)

| Table | RLS Enabled | SELECT | INSERT | UPDATE | DELETE | Authorization Basis |
|---|:---:|:---:|:---:|:---:|:---:|---|
| `users` | Yes | Own | Own | Own | Own | `id = auth.uid()` |
| `projects` | Yes | Owner | Owner | Owner | Owner | `owner_id = auth.uid()` |
| `repositories` | Yes | Owner | Owner | Owner | Owner | `has_project_access(project_id)` |
| `incidents` | Yes | Owner | Owner | Owner | Owner | `has_project_access(project_id)` |
| `investigations` | Yes | Owner | Owner | Owner | Owner | `has_project_access(project_id)` |
| `evidence` | Yes | Owner | Owner | Owner | Owner | `investigation -> project owner` |
| `deployments` | Yes | Owner | Owner | Owner | Owner | `has_project_access(project_id)` |
| `fix_proposals` | Yes | Owner | Owner | Owner | Owner | `investigation -> project owner` |
| `approvals` | Yes | Owner | Approver+Owner | Approver+Owner | Approver+Owner | `fix_proposal -> project owner & approver_id = auth.uid()` |
| `audit_logs` | Yes | Scoped | Scoped | ❌ Denied | ❌ Denied | `project owner / actor_id = auth.uid()` (Append-only) |

#### Running Migrations

```bash
cd backend

# View pending or executed migrations
alembic history
alembic heads

# Apply migrations up to head (0002_row_level_security)
alembic upgrade head

# Revert RLS migration
alembic downgrade -1
```

#### Running RLS Security Tests

```bash
cd backend

# Run full test suite (Phase 1–3 + Phase 4 RLS security tests)
pytest -v

# Run RLS security tests specifically
pytest tests/test_rls_security.py -v
```

#### Security Model & Service-Role Considerations

* **User Identity**: Identity is anchored on Supabase's `auth.uid()`, matching the `User.id` UUID primary key.
* **Defense in Depth**: Even if application-level checks fail or are bypassed, PostgreSQL RLS rejects cross-tenant reads, writes, updates, and deletes.
* **Service-Role Key**: The `SUPABASE_SERVICE_ROLE_KEY` bypasses RLS and is restricted exclusively to trusted backend worker operations (system audit logs, system-triggered background analysis). **It is never exposed to clients, frontends, or logged.**
* **Append-Only Immutability**: `audit_logs` has no UPDATE or DELETE policies for the `authenticated` role, preventing tampering with history.
* **Future Project Membership**: The `public.has_project_access(p_project_id)` `SECURITY DEFINER` function encapsulates project authorization. When team/collaborator membership tables are introduced in future phases, updating this function extends authorization platform-wide without altering table policies.

#### Phase Dependencies
* **Phase 5 (Authentication)** must provide valid user JWTs with `sub = user.id` claim for client sessions.
* **Phase 6 (User & Project APIs)** must enforce application-level authorization in FastAPI while relying on database RLS as an additional security boundary.

---

### Project Structure

```
backend/
├── app/
│   ├── api/
│   │   ├── router.py          # Root API router
│   │   └── v1/
│   │       ├── router.py      # v1 router
│   │       ├── health.py      # GET /api/v1/health
│   │       └── ready.py       # GET /api/v1/ready (DB readiness probe)
│   ├── core/
│   │   ├── config.py          # pydantic-settings configuration
│   │   ├── logging.py         # Centralized logging setup
│   │   └── exceptions.py      # Error handlers
│   ├── db/
│   │   ├── base.py            # Base, UUIDMixin, TimestampMixin
│   │   ├── session.py         # Async engine & sessionmaker
│   │   └── migrations/        # Alembic migrations
│   │       ├── env.py         # Custom migration runner (sync + asyncpg)
│   │       └── versions/
│   │           ├── 0001_initial_schema.py      # Phase 3 initial schema
│   │           └── 0002_row_level_security.py  # Phase 4 Supabase RLS
│   ├── models/                # 10 core domain models
│   └── schemas/
│       ├── health.py
│       └── ready.py
├── tests/
│   ├── conftest.py
│   ├── test_health.py
│   ├── test_database.py
│   ├── test_models_phase3.py
│   └── test_rls_security.py   # Phase 4 RLS security test suite
├── requirements.txt
├── requirements-dev.txt
├── pyproject.toml             # pytest + Ruff config
├── Dockerfile
├── .dockerignore
└── .env.example
```

---

### Phase Roadmap

| Phase | Status | Description |
|---|---|---|
| Phase 1 | ✅ **Complete** | FastAPI foundation, health endpoint, config, logging, error handling, tests |
| Phase 2 | ✅ **Complete** | Database foundation — Supabase, PostgreSQL, SQLAlchemy async engine, session |
| Phase 3 | ✅ **Complete** | Database models & relationships (10 core models, constraints, enums) |
| Phase 4 | ✅ **Complete** | Supabase Row Level Security (RLS) — policies, ownership, isolation |
| Phase 5 | 🔜 Planned | Authentication — Supabase Auth, OAuth, JWT validation |
| Phase 6 | 🔜 Planned | User & Project APIs — CRUD endpoints, workspace management |
| Phase 7 | 🔜 Planned | GitHub integration |
| Phase 8 | 🔜 Planned | AI Agent — NVIDIA Nemotron via Nebius |
| Phase 9 | 🔜 Planned | Root cause engine, fix generator, sandbox |
| Phase 10 | 🔜 Planned | Observability — metrics, tracing |

---

### Team

| Role | Owns |
|---|---|
| AI / Agent Engineer | orchestrator, agents, reasoning, evidence engine, root cause, fix generator, sandbox |
| Backend / DevOps Engineer | backend, infra, database, security, CI/CD |
| Frontend Engineer | frontend |

---

### Git Branching Strategy

| Branch | Purpose |
|---|---|
| `prd` | Production — never push directly |
| `dev` | Integration |
| `feature/*` | Feature branches — PR into `dev` |

Current feature branch: `feature/phase4-supabase-rls`

