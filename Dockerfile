# Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
FROM python:3.14-slim

LABEL org.opencontainers.image.title="HGPExamWorkFlowAndChat" \
      org.opencontainers.image.description="Course collaboration, hybrid search, assisted grading, and secure exam workflows" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.authors="Harald Glab-Plhak" \
      org.opencontainers.image.source="https://github.com/example/HGPExamWorkFlowAndChat"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    WEB_CONCURRENCY=2 \
    KEEP_ALIVE_TIMEOUT_SECONDS=10

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential gcc libpq-dev ffmpeg libpq5 openssl curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml setup.py README.md LICENSE requirements-docker-constraints.txt ./
COPY backend backend
COPY ml ml

RUN python -m pip install --no-cache-dir -c requirements-docker-constraints.txt . \
    && apt-get purge -y --auto-remove build-essential gcc libpq-dev \
    && addgroup --system app \
    && adduser --system --ingroup app --home /app app

COPY frontend frontend
COPY infra infra
COPY data data
COPY install.md run.md README.md LICENSE ./
RUN chown -R app:app /app

USER app
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"]

CMD ["sh", "-c", "uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --workers ${WEB_CONCURRENCY:-2} --timeout-keep-alive ${KEEP_ALIVE_TIMEOUT_SECONDS:-10}"]
