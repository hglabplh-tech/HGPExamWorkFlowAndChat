# Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
FROM python:3.12-slim
LABEL org.opencontainers.image.title="HcpXmlWorkflowChat" \
      org.opencontainers.image.description="Course collaboration, hybrid search, and assisted grading" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.authors="Harald Glab-Plhak"
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends openssl && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml README.md LICENSE ./
COPY backend backend
RUN pip install --no-cache-dir .
COPY frontend frontend
RUN addgroup --system app && adduser --system --ingroup app --home /app app \
    && chown -R app:app /app
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"]
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
