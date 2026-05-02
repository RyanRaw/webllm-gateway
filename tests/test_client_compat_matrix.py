from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from webai_gateway.app import create_app
from webai_gateway.config import GatewayConfig, ServerConfig, ToolBridgeConfig, UpstreamConfig


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "client_compat"


@dataclass(frozen=True)
class ClientCompatCase:
    id: str
    path: Path
    payload: dict[str, Any]


def load_client_compat_cases(root: Path) -> list[ClientCompatCase]:
    if not root.exists():
        raise ValueError(f"Client compatibility fixture root does not exist: {root}")
    cases: list[ClientCompatCase] = []
    for path in sorted(root.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise AssertionError(f"Client compatibility fixture must be a JSON object: {path}")
        for key in ("id", "description", "protocol", "request", "upstream", "expected"):
            if key not in payload:
                raise AssertionError(f"Client compatibility fixture {path} is missing required field: {key}")
        cases.append(ClientCompatCase(id=str(payload["id"]), path=path, payload=payload))
    if not cases:
        raise ValueError(f"No client compatibility fixtures found under: {root}")
    return cases


def test_client_compat_matrix_has_required_coverage() -> None:
    cases = load_client_compat_cases(FIXTURE_ROOT)
    assert len(cases) >= 10
    protocols = {case.payload["protocol"] for case in cases}
    assert {"openai_chat_completions", "anthropic_messages"} <= protocols


@pytest.mark.parametrize("case", load_client_compat_cases(FIXTURE_ROOT), ids=lambda case: case.id)
def test_client_compat_matrix_case(case: ClientCompatCase) -> None:
    payload = case.payload
    seen_upstream: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_upstream.append(json.loads(request.content.decode("utf-8")))
        upstream = payload["upstream"]
        contents = upstream.get("contents") if isinstance(upstream.get("contents"), list) else None
        if contents:
            index = min(len(seen_upstream) - 1, len(contents) - 1)
            content = str(contents[index])
        else:
            content = str(upstream["content"])
        return httpx.Response(200, json=_openai_response(content), request=request)

    raw_config = payload.get("tool_bridge_config") or {}
    config = GatewayConfig(
        server=ServerConfig(api_key="local-dev-key"),
        upstream=UpstreamConfig(base_url="http://upstream.test/v1", model="web-model"),
        tool_bridge=ToolBridgeConfig(
            mode=str(raw_config.get("mode") or "strict"),
            activation_policy=str(raw_config.get("activationPolicy") or "auto"),
            exposure_policy=str(raw_config.get("exposurePolicy") or "all"),
            tool_profile=str(raw_config.get("toolProfile") or "all"),
            max_calls_per_turn=int(raw_config.get("maxCallsPerTurn") or 4),
        ),
    )
    client = TestClient(create_app(config=config, http_client=httpx.Client(transport=httpx.MockTransport(handler))))

    protocol = payload["protocol"]
    if protocol == "openai_chat_completions":
        response = client.post("/v1/chat/completions", headers=_headers(), json=payload["request"])
    elif protocol == "anthropic_messages":
        response = client.post(
            "/v1/messages",
            headers={**_headers(), "anthropic-version": "2023-06-01"},
            json=payload["request"],
        )
    else:
        raise AssertionError(f"Unsupported client compatibility protocol: {protocol}")

    expected = payload["expected"]
    assert response.status_code == int(expected.get("status") or 200), case.id
    for name, value in (expected.get("headers") or {}).items():
        assert response.headers[name] == value, case.id
    assert len(seen_upstream) == int(expected.get("upstreamCalls") or 1), case.id
    for key in expected.get("upstreamOmits") or []:
        assert key not in seen_upstream[0], case.id
    upstream_contains = expected.get("upstreamMessageContains")
    if upstream_contains:
        assert upstream_contains in json.dumps(seen_upstream[0].get("messages"), ensure_ascii=False), case.id

    body = response.json()
    if protocol == "openai_chat_completions":
        _assert_openai_expected(body, expected, case.id)
    else:
        _assert_anthropic_expected(body, expected, case.id)


def _openai_response(content: str) -> dict[str, Any]:
    return {
        "id": "upstream-chatcmpl",
        "object": "chat.completion",
        "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": content}}],
    }


def _headers() -> dict[str, str]:
    return {"Authorization": "Bearer local-dev-key"}


def _assert_openai_expected(body: dict[str, Any], expected: dict[str, Any], case_id: str) -> None:
    choice = body["choices"][0]
    if expected.get("finishReason"):
        assert choice["finish_reason"] == expected["finishReason"], case_id
    text_contains = expected.get("textContains")
    if text_contains:
        assert text_contains in str(choice["message"].get("content") or ""), case_id
    tool_call = expected.get("toolCall")
    if tool_call:
        actual = choice["message"]["tool_calls"][0]
        assert actual["function"]["name"] == tool_call["name"], case_id
        assert json.loads(actual["function"]["arguments"]) == tool_call["input"], case_id


def _assert_anthropic_expected(body: dict[str, Any], expected: dict[str, Any], case_id: str) -> None:
    if expected.get("stopReason"):
        assert body["stop_reason"] == expected["stopReason"], case_id
    text_contains = expected.get("textContains")
    if text_contains:
        text = "\n".join(block.get("text", "") for block in body["content"] if block.get("type") == "text")
        assert text_contains in text, case_id
    tool_call = expected.get("toolCall")
    if tool_call:
        actual = next(block for block in body["content"] if block.get("type") == "tool_use")
        assert actual["name"] == tool_call["name"], case_id
        assert actual["input"] == tool_call["input"], case_id
