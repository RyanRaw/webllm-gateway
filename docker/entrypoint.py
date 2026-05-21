from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys


APP_ROOT = Path(os.environ.get("WEBAI_APP_ROOT", "/app"))
DATA_ROOT = Path(os.environ.get("WEBAI_DATA_ROOT", "/data"))
CONFIG_PATH = Path(os.environ.get("WEBAI_CONFIG_PATH", DATA_ROOT / "config.json"))
CONFIG_TEMPLATE = Path(os.environ.get("WEBAI_CONFIG_TEMPLATE", APP_ROOT / "config.example.json"))
DEFAULT_CONTAINER_HOST = ("host", "0.0.0.0")
DEFAULT_UPSTREAM_BASE_URL = "http://host.docker.internal:8500/v1"
DEFAULT_DEEPSEEK_DS2API_BASE_URL = "http://host.docker.internal:9331/v1"
SUPERVISOR_COMMAND_TEXT = "python -m webai_gateway.runtime_supervisor --config config.json --ensure"
GATEWAY_COMMAND_TEXT = "python -m webai_gateway"


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args != ["serve"]:
        os.execvp(args[0], args)
        return 0

    _ensure_config()
    if _env_flag("WEBAI_RUN_RUNTIME_SUPERVISOR", default=True):
        subprocess.run(
            SUPERVISOR_COMMAND_TEXT.split(),
            cwd=str(CONFIG_PATH.parent),
            check=True,
        )
    os.execvp("python", GATEWAY_COMMAND_TEXT.split())
    return 0


def _ensure_config() -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    created = not CONFIG_PATH.exists()
    if created:
        config = json.loads(CONFIG_TEMPLATE.read_text(encoding="utf-8"))
        _set(config, ("server", DEFAULT_CONTAINER_HOST[0]), os.environ.get("WEBAI_HOST", DEFAULT_CONTAINER_HOST[1]))
        _set(config, ("server", "port"), int(os.environ.get("WEBAI_PORT", "8610")))
        _set(config, ("upstream", "baseUrl"), os.environ.get("WEBAI_UPSTREAM_BASE_URL", DEFAULT_UPSTREAM_BASE_URL))
        _set(
            config,
            ("providerRuntime", "deepseekDs2apiBaseUrl"),
            os.environ.get("WEBAI_DEEPSEEK_DS2API_BASE_URL", DEFAULT_DEEPSEEK_DS2API_BASE_URL),
        )
    else:
        config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))

    _set_from_env(config, ("server", "host"), "WEBAI_HOST")
    _set_int_from_env(config, ("server", "port"), "WEBAI_PORT")
    _set_from_env(config, ("server", "apiKey"), "WEBAI_API_KEY")
    _set_from_env(config, ("upstream", "baseUrl"), "WEBAI_UPSTREAM_BASE_URL")
    _set_from_env(config, ("upstream", "apiKey"), "WEBAI_UPSTREAM_API_KEY")
    _set_from_env(config, ("upstream", "model"), "WEBAI_UPSTREAM_MODEL")
    _set_from_env(config, ("providerRuntime", "deepseekDs2apiBaseUrl"), "WEBAI_DEEPSEEK_DS2API_BASE_URL")

    CONFIG_PATH.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _set_from_env(config: dict[str, object], path: tuple[str, ...], env_name: str) -> None:
    value = os.environ.get(env_name)
    if value is not None and value.strip():
        _set(config, path, value)


def _set_int_from_env(config: dict[str, object], path: tuple[str, ...], env_name: str) -> None:
    value = os.environ.get(env_name)
    if value is not None and value.strip():
        _set(config, path, int(value))


def _set(config: dict[str, object], path: tuple[str, ...], value: object) -> None:
    current: dict[str, object] = config
    for key in path[:-1]:
        child = current.get(key)
        if not isinstance(child, dict):
            child = {}
            current[key] = child
        current = child
    current[path[-1]] = value


def _env_flag(name: str, *, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off"}


if __name__ == "__main__":
    raise SystemExit(main())
