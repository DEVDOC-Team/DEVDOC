# DEVDOC backend — Phase 2 image
# Base: python:3.13-slim  |  User: appuser (non-root)
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_HOME=/app

WORKDIR ${APP_HOME}

# System dependencies: curl (health probes) + libpq (asyncpg needs no system libpq,
# but psycopg2-binary does; using asyncpg only so libpq not needed here)
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies (layer-cached before source copy)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY . .

EXPOSE 8000

# Runtime environment defaults (no secrets — inject via docker run -e or compose)
ENV APP_NAME="DEVDOC API" \
    APP_VERSION="0.1.0" \
    ENVIRONMENT="production" \
    DEBUG="false" \
    HOST="0.0.0.0" \
    PORT="8000"

# Non-root user for security
RUN useradd --create-home --shell /bin/bash appuser \
    && chown -R appuser:appuser ${APP_HOME}

USER appuser

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health || exit 1

# Apply pending schema migrations before starting the API. Alembic exits
# successfully without changing the schema when the database is already current.
CMD ["/bin/sh", "-c", "python -m alembic upgrade head && python -m alembic current && exec python -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
