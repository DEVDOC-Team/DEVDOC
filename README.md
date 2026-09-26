# DEVDOC

**DEVDOC** is an AI-powered DevOps and SRE platform that helps development teams investigate application, infrastructure, and deployment problems — and propose verified fixes.

> ⚠️ **Phase 1 — Backend Foundation only.** The platform is under active development. Not all features are available yet.

---

## Backend — Phase 1 Foundation

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

### Project Structure

```
backend/
├── app/
│   ├── api/
│   │   ├── router.py          # Root API router
│   │   └── v1/
│   │       ├── router.py      # v1 router
│   │       └── health.py      # GET /api/v1/health
│   ├── core/
│   │   ├── config.py          # pydantic-settings configuration
│   │   ├── logging.py         # Centralized logging setup
│   │   └── exceptions.py      # Error handlers
│   ├── schemas/
│   │   └── health.py          # HealthResponse schema
│   └── main.py                # FastAPI application
├── tests/
│   ├── conftest.py
│   └── test_health.py
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
| Phase 2 | 🔜 Planned | Database — PostgreSQL, Supabase, SQLAlchemy, Alembic |
| Phase 3 | 🔜 Planned | Authentication — OAuth, JWT |
| Phase 4 | 🔜 Planned | GitHub integration |
| Phase 5 | 🔜 Planned | AI Agent — NVIDIA Nemotron via Nebius |
| Phase 6 | 🔜 Planned | Root cause engine, fix generator, sandbox |
| Phase 7 | 🔜 Planned | Security hardening, rate limiting, audit logs |
| Phase 8 | 🔜 Planned | Observability — metrics, tracing |

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

Current feature branch: `feature/backend-foundation`
