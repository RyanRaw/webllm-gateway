# syntax=docker/dockerfile:1

FROM node:22-bookworm-slim AS webui-builder
WORKDIR /src/webui

COPY webui/package.json webui/pnpm-lock.yaml webui/pnpm-workspace.yaml ./
RUN corepack enable && corepack pnpm install --frozen-lockfile

COPY webui/ ./
RUN corepack pnpm build

FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY webai_gateway/ ./webai_gateway/
COPY config.example.json README.md LICENSE NOTICE.md THIRD_PARTY_NOTICES.md ./
COPY docs/ ./docs/
COPY examples/ ./examples/
COPY docker/ ./docker/
COPY --from=webui-builder /src/webui/dist ./webui/dist

WORKDIR /data
EXPOSE 8610

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import json,urllib.request; data=json.load(urllib.request.urlopen('http://127.0.0.1:8610/health', timeout=3)); raise SystemExit(0 if data.get('ok') else 1)"

ENTRYPOINT ["python", "/app/docker/entrypoint.py"]
CMD ["serve"]
