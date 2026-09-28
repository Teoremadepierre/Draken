FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# lxml needs libxml2/libxslt at runtime; curl is for the healthcheck.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libxml2 libxslt1.1 curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install dependencies first so the layer caches across source changes.
COPY backend/pyproject.toml /app/backend/pyproject.toml
COPY backend/draken/__init__.py /app/backend/draken/__init__.py
RUN pip install --no-cache-dir -e "/app/backend[postgres]"

COPY backend /app/backend
COPY frontend /app/frontend
COPY data/seeds /app/data/seeds
COPY scripts /app/scripts

RUN useradd --system --create-home draken \
    && mkdir -p /app/data \
    && chown -R draken:draken /app
USER draken

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/api/health || exit 1

CMD ["uvicorn", "draken.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
