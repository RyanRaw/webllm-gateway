from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from webai_gateway.config import ToolBridgeConfig
from webai_gateway.tool_bridge import build_context, parse_tool_response, prefer_local_tools_for_local_agent_task


@dataclass(frozen=True)
class ReplayCase:
    id: str
    path: Path
    payload: dict[str, Any]


def load_replay_cases(root: Path) -> list[ReplayCase]:
    if not root.exists():
        raise ValueError(f"Replay fixture root does not exist: {root}")
    cases: list[ReplayCase] = []
    for path in sorted(root.glob("*.json")):
        payload = _load_json_object(path)
        _validate_replay_payload(payload, path)
        cases.append(ReplayCase(id=str(payload["id"]), path=path, payload=payload))
    if not cases:
        raise ValueError(f"No replay fixtures found under: {root}")
    return cases


def run_replay_case(case: ReplayCase) -> dict[str, Any]:
    payload = case.payload
    _validate_replay_payload(payload, case.path)
    raw_config = payload.get("tool_bridge_config") or {}
    config = ToolBridgeConfig(
        mode=str(raw_config.get("mode") or "strict"),
        activation_policy=str(raw_config.get("activationPolicy") or "auto"),
        exposure_policy=str(raw_config.get("exposurePolicy") or "all"),
        tool_profile=str(raw_config.get("toolProfile") or "auto"),
        max_calls_per_turn=int(raw_config.get("maxCallsPerTurn") or 4),
    )
    input_payload = payload["input"]
    context = build_context(input_payload["tools"], config, model=str(payload.get("model") or ""))
    messages = input_payload.get("messages")
    if not isinstance(messages, list):
        messages = [{"role": "user", "content": str(input_payload.get("task_text") or "")}]
    context = prefer_local_tools_for_local_agent_task(
        context,
        messages,
    )
    result = parse_tool_response(str(input_payload["model_text"]), context)
    return {
        "error": result.error.kind if result.error else None,
        "warning": result.warning,
        "tool_calls": [
            {"id": call.id, "name": call.name, "input": call.input}
            for call in result.tool_calls
        ],
    }


def _load_json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Replay fixture is not valid JSON: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"Replay fixture must be a JSON object: {path}")
    return payload


def _validate_replay_payload(payload: dict[str, Any], path: Path) -> None:
    for key in ("id", "description", "protocol", "input", "expected"):
        if key not in payload:
            raise AssertionError(f"Replay fixture {path} is missing required field: {key}")
    if not isinstance(payload["id"], str) or not payload["id"].strip():
        raise AssertionError(f"Replay fixture {path} field 'id' must be a non-empty string")
    if not isinstance(payload["input"], dict):
        raise AssertionError(f"Replay fixture {payload['id']} field 'input' must be an object")
    if not isinstance(payload["expected"], dict):
        raise AssertionError(f"Replay fixture {payload['id']} field 'expected' must be an object")
    input_payload = payload["input"]
    for key in ("task_text", "tools", "model_text"):
        if key not in input_payload:
            raise AssertionError(f"Replay fixture {payload['id']} input is missing required field: {key}")
    if not isinstance(input_payload["tools"], list):
        raise AssertionError(f"Replay fixture {payload['id']} input.tools must be a list")
    expected = payload["expected"]
    for key in ("error", "tool_calls", "warning_contains"):
        if key not in expected:
            raise AssertionError(f"Replay fixture {payload['id']} expected is missing required field: {key}")
    if expected["error"] is not None and not isinstance(expected["error"], str):
        raise AssertionError(f"Replay fixture {payload['id']} expected.error must be a string or null")
    if not isinstance(expected["tool_calls"], list):
        raise AssertionError(f"Replay fixture {payload['id']} expected.tool_calls must be a list")
    if expected["warning_contains"] is not None and not isinstance(expected["warning_contains"], str):
        raise AssertionError(f"Replay fixture {payload['id']} expected.warning_contains must be a string or null")
