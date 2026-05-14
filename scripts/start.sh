#!/usr/bin/env bash
# Pi Backend release-phase + app start.
# Called by Railway via railway.toml startCommand. Keeping the wiring in a
# real script means we can use proper shell features (set -e, exec, ${VAR:-default})
# without escape-hell when expressing the same logic inline in railway.toml.
set -euo pipefail

echo "[start] alembic begin"
alembic upgrade head
echo "[start] alembic done, PORT=${PORT:-unset}"

# exec replaces the shell process with gunicorn so it receives signals
# directly (cleaner Railway shutdown handling).
exec gunicorn app.main:app \
    --worker-class=uvicorn.workers.UvicornWorker \
    --bind="0.0.0.0:${PORT:-8000}" \
    --workers=2 \
    --timeout=60 \
    --access-logfile=- \
    --error-logfile=- \
    --log-level=info
