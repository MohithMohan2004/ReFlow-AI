# syntax=docker/dockerfile:1

# ---- 1. Build the React frontend into static/app ----
FROM node:22-slim AS frontend
WORKDIR /build/frontend
ARG NPM_REGISTRY=https://registry.npmjs.org/
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --registry=$NPM_REGISTRY
COPY frontend/ ./
RUN npm run build   # writes to /build/static/app

# ---- 2. Python runtime (Flask + gunicorn) ----
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=10000

# libgomp1 is needed by xgboost
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
COPY --from=frontend /build/static/app ./static/app

RUN mkdir -p uploads && useradd -m reflow && chown -R reflow /app
USER reflow

EXPOSE 10000
# HTTP/1.1 only: TLS and HTTP/2 end at the Azure ingress, so gunicorn never
# parses HTTP/2 frames (CVE-2023-44487 "Rapid Reset" is handled there).
# Header limits are gunicorn's defaults, made explicit. 75 s covers the slowest
# request (an OCEMS vendor test call, capped at about 60 s); long work runs in
# background threads.
CMD ["sh", "-c", "exec gunicorn app:app --bind 0.0.0.0:${PORT} --http-protocols h1 --timeout 75 --graceful-timeout 30 --keep-alive 5 --limit-request-line 4094 --limit-request-fields 100 --limit-request-field_size 8190 --workers ${WEB_CONCURRENCY:-2}"]
