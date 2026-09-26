# DEVDOC backend — Phase 1 foundation image
# Base: python:3.13-slim  |  User: appuser (non-root)
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_HOME=/app

WORKDIR ${APP_HOME}

# Install only what is needed at runtime
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies first (improves layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY . .

EXPOSE 8000

# Runtime environment defaults (no secrets; override via docker run -e or compose)
ENV APP_NAME="DEVDOC API" \
    APP_VERSION="0.1.0" \
    ENVIRONMENT="production" \
    DEBUG="false" \
    HOST="0.0.0.0" \
    PORT="8000"

# Create a non-root user and hand over ownership
RUN useradd --create-home --shell /bin/bash appuser \
    && chown -R appuser:appuser ${APP_HOME}

USER appuser

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
