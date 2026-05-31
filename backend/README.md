# Backend — Workforce Management System (FastAPI)

V0 foundations: app skeleton, config, Postgres/Redis connection layers, Celery
app, Alembic config, health endpoints. No domain logic yet.

## Run (host, against Dockerized datastores)
```bash
cp .env.example .env
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8100
```
Docs: http://localhost:8100/api/v1/docs · Health: http://localhost:8100/api/v1/health

## Tests
```bash
pytest
```

## Migrations (from V1, once models exist)
```bash
alembic revision --autogenerate -m "message"
alembic upgrade head
```

Structure and conventions: see `../docs/V1_ARCHITECTURE_PACKAGE.md` §6 and `../docs/api/openapi-v1.yaml`.
