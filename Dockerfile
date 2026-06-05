# syntax=docker/dockerfile:1

# ---- Stage 1: build the Vite/React frontend into dist/ ----
FROM node:22-slim AS frontend
WORKDIR /frontend
# Copy manifests first for layer caching, then install with the committed lock.
COPY src/jobhunter/web/frontend/package.json src/jobhunter/web/frontend/package-lock.json ./
RUN npm ci
COPY src/jobhunter/web/frontend/ ./
RUN npm run build

# ---- Stage 2: Python runtime with WeasyPrint's native libraries ----
# Pinned to bookworm: trixie's t64 transition renamed libffi8 -> libffi8t64
# (and friends), which would break the apt step below.
FROM python:3.12-slim-bookworm AS runtime

# WeasyPrint renders the ATS PDF via Pango/Cairo — these native libs are
# mandatory; without them `import weasyprint` / PDF export fails at runtime.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpango-1.0-0 \
        libpangoft2-1.0-0 \
        libharfbuzz0b \
        libgdk-pixbuf-2.0-0 \
        libcairo2 \
        libffi8 \
        shared-mime-info \
        fonts-dejavu-core \
        supervisor \
    && rm -rf /var/lib/apt/lists/*

# Caddy: copy the static binary from the official image (no apt repo needed).
COPY --from=caddy:2.11 /usr/bin/caddy /usr/bin/caddy

WORKDIR /app

# Project metadata + source. Editable install keeps PROJECT_ROOT = /app, so
# canonical-cv.json, config.yaml, schemas/, out/, and .cost-ledger.json all
# resolve under the /app tree (some are bind-mounted by docker-compose).
COPY pyproject.toml README.md ./
COPY src/ ./src/
# The frontend is served as static files from this exact path (api.py:
# FRONTEND_DIST = .../frontend/dist). Pull it from the build stage.
COPY --from=frontend /frontend/dist/ ./src/jobhunter/web/frontend/dist/

RUN pip install --no-cache-dir -e ".[web]"

# Repo-root runtime inputs read via PROJECT_ROOT. canonical-cv.json + config.yaml
# are baked as sensible defaults but meant to be overridden by bind mounts.
# .env is NEVER baked — secrets arrive through the container environment.
COPY canonical-cv.json config.yaml ./
COPY schemas/ ./schemas/

# Baked config: Caddyfile (front door) + supervisord (process manager).
COPY Caddyfile /etc/caddy/Caddyfile
COPY docker/supervisord.conf /etc/supervisor/supervisord.conf

# Non-root app user for uvicorn; Caddy runs as root for 80/443 + cert storage.
RUN useradd --create-home --uid 10001 app \
    && mkdir -p /app/out /data /config \
    && touch /app/.cost-ledger.json \
    && chown -R app:app /app

# Baked default so direct `docker run ... jobhunter` debug invocations bind the
# right port; supervisord sets this per-program too (redundant but harmless).
ENV JOBHUNTER_WEB_PORT=8765

# Caddy listens here in prod (TLS) / :8080 in local. EXPOSE is documentation.
EXPOSE 8080 80 443

# supervisord (PID 1) runs uvicorn (loopback) + Caddy (public) together.
CMD ["supervisord", "-c", "/etc/supervisor/supervisord.conf"]
