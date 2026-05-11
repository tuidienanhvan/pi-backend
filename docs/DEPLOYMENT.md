# Deployment

## Backend (Python/FastAPI)
```bash
uv sync
uv run alembic upgrade head
uv run hypercorn app.main:app --bind 0.0.0.0:8000
```

## Dashboard (React/Vite)
```bash
npm run build
# Output: dist/
```

## WordPress Plugin
```bash
# Build zips in /dist/
ls dist/plugins/*.zip
```

## Environment Variables
- `DATABASE_URL`
- `REDIS_URL`
- `STRIPE_SECRET_KEY`
- `JWT_SECRET_KEY`