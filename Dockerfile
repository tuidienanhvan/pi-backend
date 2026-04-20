# ──────────────────────────────────────────────────────────────
# Pi Backend — multi-stage production Dockerfile
# ──────────────────────────────────────────────────────────────
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# System deps (lxml needs libxml2, postgres needs libpq)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    libxml2-dev \
    libxslt1-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# ─── Dependencies layer (cache-friendly) ─────────────────────
FROM base AS deps

COPY requirements.txt .
RUN pip install -r requirements.txt

# ─── Runtime layer ───────────────────────────────────────────
FROM deps AS runtime

COPY app        ./app
COPY migrations ./migrations
COPY alembic.ini .
COPY scripts    ./scripts

# Create non-root user
RUN groupadd -r pi && useradd -r -g pi pi \
    && mkdir -p /app/data /app/logs \
    && chown -R pi:pi /app

USER pi

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Default: 2 workers × uvicorn workers — Railway/Fly override with WEB_CONCURRENCY
ENV WEB_CONCURRENCY=2
CMD ["gunicorn", "app.main:app", \
     "--worker-class=uvicorn.workers.UvicornWorker", \
     "--bind=0.0.0.0:8000", \
     "--access-logfile=-", \
     "--error-logfile=-", \
     "--timeout=60"]
