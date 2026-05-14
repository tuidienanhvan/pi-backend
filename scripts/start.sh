#!/usr/bin/env bash
# Pi Backend — Railway release + serve.
# Run migrations, then hand off to gunicorn via exec so signals reach
# the worker process directly (clean shutdown).
set -euo pipefail

alembic upgrade head

exec gunicorn app.main:app \
    --worker-class=uvicorn.workers.UvicornWorker \
    --bind="0.0.0.0:${PORT:-8000}" \
    --workers=2 \
    --timeout=60 \
    --access-logfile=- \
    --error-logfile=- \
    --log-level=info
