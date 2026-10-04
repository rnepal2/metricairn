FROM node:22-alpine AS frontend
WORKDIR /build
COPY apps/web/package*.json ./apps/web/
COPY packages/tracker/package*.json ./packages/tracker/
RUN npm --prefix apps/web ci && npm --prefix packages/tracker ci
COPY apps/web ./apps/web
COPY packages/tracker/src ./packages/tracker/src
RUN npm --prefix apps/web run build && npm --prefix packages/tracker run build

FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.11.8 /uv /usr/local/bin/uv
WORKDIR /srv
COPY pyproject.toml uv.lock LICENSE ./
COPY apps/api/pyproject.toml ./apps/api/pyproject.toml
COPY apps/mcp-server/pyproject.toml ./apps/mcp-server/pyproject.toml
COPY apps/api/app ./apps/api/app
COPY apps/mcp-server/metricairn_mcp ./apps/mcp-server/metricairn_mcp
RUN uv sync --locked --no-dev && useradd --create-home --uid 10001 metricairn \
    && mkdir -p /srv/data /srv/static /srv/web && chown -R metricairn:metricairn /srv
COPY --from=frontend /build/packages/tracker/dist/metricairn.js /srv/static/metricairn.js
COPY --from=frontend /build/apps/web/dist /srv/web
USER metricairn
ENV PATH="/srv/.venv/bin:$PATH"
ENV DATABASE_URL=sqlite:///./data/metricairn.db TRACKER_DIST=/srv/static WEB_DIST=/srv/web SCHEDULER_ENABLED=false
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/ready', timeout=2)"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
