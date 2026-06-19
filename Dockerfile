FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APPLYPILOT_SAAS_DB=/data/applypilot.sqlite3 \
    APPLYPILOT_WEB_DIR=/app/apps/web

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
COPY apps/web ./apps/web

RUN pip install --no-cache-dir '.[server]'

RUN mkdir -p /data
VOLUME ["/data"]
EXPOSE 8787

CMD ["applypilot", "--workspace", "/data", "serve", "--host", "0.0.0.0", "--port", "8787", "--db", "/data/applypilot.sqlite3", "--web-dir", "/app/apps/web"]
