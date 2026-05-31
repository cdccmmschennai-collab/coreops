FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# System deps kept minimal; psycopg[binary] needs no build toolchain.
COPY requirements.txt .
# Resilient install: upgrade pip, add retries/timeout (build-network can truncate
# the package index on flaky links).
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir --retries 8 --timeout 180 -r requirements.txt

COPY . .

EXPOSE 8000

# Default command is overridden by docker-compose (uvicorn / celery).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
