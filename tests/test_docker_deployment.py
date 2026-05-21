from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_docker_image_entrypoint_creates_runtime_config_for_container() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    entrypoint = (ROOT / "docker" / "entrypoint.py").read_text(encoding="utf-8")

    assert "FROM node:" in dockerfile
    assert "corepack pnpm build" in dockerfile
    assert "FROM python:" in dockerfile
    assert "WORKDIR /data" in dockerfile
    assert "EXPOSE 8610" in dockerfile
    assert "docker/entrypoint.py" in dockerfile
    assert "python -m webai_gateway.runtime_supervisor --config config.json --ensure" in entrypoint
    assert "python -m webai_gateway" in entrypoint
    assert '"host", "0.0.0.0"' in entrypoint
    assert "WEBAI_API_KEY" in entrypoint
    assert "WEBAI_UPSTREAM_BASE_URL" in entrypoint
    assert "WEBAI_DEEPSEEK_DS2API_BASE_URL" in entrypoint


def test_docker_compose_keeps_user_state_outside_image_and_reaches_host_runtimes() -> None:
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    assert "webllm-gateway" in compose
    assert '"8610:8610"' in compose
    assert "webai-gateway-data:/data" in compose
    assert "host.docker.internal:host-gateway" in compose
    assert "WEBAI_UPSTREAM_BASE_URL=http://host.docker.internal:8500/v1" in compose
    assert "WEBAI_DEEPSEEK_DS2API_BASE_URL=http://host.docker.internal:9331/v1" in compose
    assert "HEALTHCHECK" not in compose


def test_readme_documents_docker_deploy_without_bundling_third_party_runtimes() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "Docker 部署" in readme
    assert "docker compose up -d --build" in readme
    assert "http://127.0.0.1:8610/" in readme
    assert "webai-gateway-data" in readme
    assert "WebAI2API / ds2api" in readme
    assert "host.docker.internal" in readme
