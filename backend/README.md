# DEVDOC Backend

The backend provides DEVDOC's versioned REST API, persistence and authorization layer, and the services that coordinate incident investigations. It is organized into two main packages:

- `app/` serves the HTTP API and implements business services, authentication, database access, and configuration.
- `orchestrator/` coordinates investigation stages, agents, evidence processing, reasoning, and optional verification integrations.

## Technology stack

| Area | Technology | Use |
| --- | --- | --- |
| Runtime | Python 3.13 | Backend runtime and Docker image base |
| HTTP API | FastAPI, Uvicorn | Async REST API and ASGI server |
| Validation and settings | Pydantic v2, pydantic-settings | Request/response schemas and environment configuration |
| Persistence | SQLAlchemy 2 async, PostgreSQL, asyncpg | ORM, asynchronous database access, and connection pooling |
| Local/test database | SQLite, aiosqlite | Lightweight development fallback and isolated tests |
| Migrations | Alembic | Versioned schema changes in `app/db/migrations/versions/` |
| Authentication | Supabase JWT verification | Bearer-token identity and authorization checks |
| Integrations | HTTPX, GitHub API, optional Nebius and Tavily providers | Repository inspection, opt-in LLM reasoning, and opt-in knowledge search |
| Rate limiting | Redis (optional/shared) | Shared rate-limit state when configured |
| Tests and lint | pytest, pytest-asyncio, HTTPX, Ruff | Automated tests and static checks |
| Container | Docker | Python 3.13 slim image running as a non-root user |

Runtime and development dependencies are listed in `requirements.txt` and `requirements-dev.txt` respectively.

## Backend structure

```text
backend/
├── app/
│   ├── main.py                  # FastAPI application, middleware, health metrics, error handlers
│   ├── dependencies.py          # Authentication and project-access dependencies
│   ├── api/
│   │   ├── router.py            # Top-level API router
│   │   └── v1/                  # Versioned endpoint modules and router registration
│   ├── core/                    # Settings, security, logging, telemetry, metrics, rate limits
│   ├── db/
│   │   ├── base.py              # Declarative base and shared database helpers
│   │   ├── session.py           # Async SQLAlchemy engines and session dependencies
│   │   └── migrations/
│   │       ├── env.py           # Alembic runtime configuration
│   │       └── versions/        # Ordered schema migrations (0001–0008)
│   ├── models/                  # SQLAlchemy ORM models
│   ├── schemas/                 # Pydantic request and response models
│   └── services/                # API business logic and database operations
├── orchestrator/
│   ├── agents/                  # GitHub, Docker, and monitoring agents/providers
│   ├── contracts/               # Agent, stage, and workflow interfaces
│   ├── core/                    # Context, execution results, errors, and orchestration engine
│   ├── evidence/                # Evidence normalization, validation, deduplication, and assembly
│   ├── fixes/                   # Remediation proposal generation and safety checks
│   ├── knowledge/               # Bounded knowledge search and providers
│   ├── llm/                     # LLM provider adapters, budgets, caching, and service
│   ├── rca/                     # Root-cause analysis models, prompts, and service
│   ├── sandbox/                 # Verification contracts and sandbox providers
│   ├── stages/                  # Investigation stage registry and stage implementations
│   └── tests/                   # Orchestrator component tests
├── scripts/                     # Developer and demonstration scripts
├── tests/                       # API, service, database, integration, and security tests
│   └── load/                    # Locust load-test scenarios
├── .env.example                 # Environment-variable template; contains no real credentials
├── alembic.ini                  # Alembic configuration
├── Dockerfile                   # Container image definition
├── pyproject.toml               # pytest and Ruff configuration
├── requirements.txt             # Runtime dependencies
└── requirements-dev.txt         # Runtime plus development/test dependencies
```

### API modules

The versioned router in `app/api/v1/router.py` registers these domains under `/api/v1`:

- `health.py`, `ready.py` — liveness and dependency readiness checks.
- `auth.py`, `users.py` — authentication/profile endpoints.
- `projects.py`, `github.py` — project management and GitHub integration.
- `incidents.py`, `investigations.py` — incident and investigation workflows.
- `chat.py`, `approvals.py` — incident-scoped chat and human approval endpoints.

The root application also exposes `/metrics` when metrics are enabled. Interactive API docs are available at `/docs` outside production mode.

## How the project is structured

Typical request flow:

```text
HTTP request
    ↓
app/api/v1 route
    ↓
app/dependencies.py (identity and project authorization)
    ↓
app/services (business rules and transaction work)
    ↓
app/models + app/db (SQLAlchemy and PostgreSQL/Supabase)
```

Route handlers stay focused on HTTP parsing and response construction. Services implement domain rules and state transitions. Pydantic schemas define API boundaries, while SQLAlchemy models and Alembic migrations define persistence. Authenticated database operations use project-level checks and database row-level security where configured.

Investigation requests can pass from `app/services/investigation.py` into `orchestrator/`. The orchestrator runs registered stages with a validated investigation context and typed results. Agent, evidence, LLM, knowledge-search, root-cause, fix-generation, and sandbox-verification components are separated into their own packages. Nebius LLM reasoning and Tavily knowledge search are opt-in and disabled by default.

## Local development

Run these commands from the `backend/` directory.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
```

Set the required database and Supabase values in `.env`. Keep secrets in this backend-only file and never commit it. If `DATABASE_URL` is omitted, the app can fall back to an in-memory SQLite database; use PostgreSQL/Supabase for persistent development data and migrations.

Apply migrations explicitly before using a persistent database. The application does not create or migrate tables automatically on startup.

```powershell
python -m alembic upgrade head
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Useful local URLs:

- `http://localhost:8000/` — service status.
- `http://localhost:8000/api/v1/health` — liveness probe.
- `http://localhost:8000/api/v1/ready` — readiness and database check.
- `http://localhost:8000/docs` — interactive API docs outside production mode.
- `http://localhost:8000/metrics` — Prometheus-format metrics when enabled.

## Tests and lint

```powershell
python -m pytest -v
python -m ruff check .
```

Pytest discovers tests in `tests/` and `orchestrator/tests/`. Load-test scenarios live in `tests/load/` and are excluded from the default pytest run.

## Docker

Build the image from this directory with `docker build -t devdoc-backend .`. The container uses Python 3.13 slim, runs as the non-root `appuser`, listens on port `8000`, and checks `/api/v1/health`. Configure secrets and connection URLs through the deployment environment. Apply Alembic migrations before starting the service against a production database.

For broader product architecture and security details, see the [repository README](../README.md) and [security guide](../SECURITY.md).
