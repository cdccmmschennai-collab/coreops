#!/bin/sh
# Backend container entrypoint: apply migrations, then run the given command.
# Scoped to the `backend` service in docker-compose (the `worker` does NOT use
# this, so migrations run exactly once).
set -e

echo "[entrypoint] applying database migrations…"
alembic upgrade head

echo "[entrypoint] starting: $*"
exec "$@"
