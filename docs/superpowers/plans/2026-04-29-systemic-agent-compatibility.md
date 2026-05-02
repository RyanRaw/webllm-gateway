# Systemic Agent Compatibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make WebAI Gateway reliably support Claude Code, KrisAI, and other agent clients by turning real failures into replayable tests and by treating webpage model tool output as a compiled protocol artifact, not trusted text.

**Architecture:** Keep Gateway as a protocol adapter only. Add a sanitized replay corpus, a deterministic ToolBridge compiler pipeline, stricter task-aware tool exposure, provider completeness guards, and admin diagnostics that show exactly where a request failed without exposing secrets.

**Tech Stack:** Python 3.11, FastAPI, pytest, httpx MockTransport, OpenAI Chat Completions compatibility, Anthropic Messages compatibility, Qwen Web/Qwen Coder direct providers, Vite web UI.

---

## Product Boundary

This plan must preserve the repository rules:

- Gateway never executes local tools, MCP, browser automation, filesystem writes, or terminal commands.
- Gateway never adds KrisAI-only, Claude Code-only, Qwen-only, or task-name-only business branches.
- All compatibility logic must be expressed as protocol behavior, provider capability, model capability, tool exposure policy, or configurable Gateway strategy.
- Gateway may reject, normalize, repair, or compile tool calls, but downstream clients remain responsible for actually executing tools and enforcing permissions.
- Logs, diagnostics, fixtures, and UI must not store cookies, bearer tokens, session tokens, API keys, private paths containing credentials, or full sensitive request bodies.

## File Structure

- Modify `webai_gateway/tool_bridge.py`
  - Keep public functions stable: `build_context`, `prepare_openai_messages`, `parse_tool_response`, `compress_observation`.
  - Internally split the current parsing flow into named phases with per-phase diagnostics.
- Create `webai_gateway/tool_bridge_replay.py`
  - Load sanitized replay fixtures.
  - Execute fixture assertions against `ToolBridgeContext`.
  - Provide helpers for unit tests and an optional CLI.
- Create `tests/fixtures/tool_bridge_replays/*.json`
  - One sanitized fixture per recurring real-world failure family.
- Create `tests/test_tool_bridge_replay.py`
  - Run all replay fixtures as parameterized tests.
- Modify `webai_gateway/app.py`
  - Record structured request diagnostics and tool compiler phase diagnostics.
  - Expose safe admin diagnostics through existing admin endpoints.
- Modify `webai_gateway/openai_api.py`
  - Keep OpenAI-compatible rejection responses deterministic and Chinese by default.
- Modify `webai_gateway/anthropic_api.py`
  - Keep Anthropic `tool_use` / `tool_result` conversion compatible with the same ToolBridge compiler path.
- Modify `webai_gateway/config.py`
  - Add replay/diagnostic/tool profile configuration with safe defaults.
- Modify `config.example.json`
  - Document new safe defaults.
- Modify `webai_gateway/static/app.js`
  - Surface diagnostics summary in Chinese without secrets.
- Modify `webai_gateway/static/index.html`
  - Only if new diagnostic UI needs a mount point.
- Test `tests/test_gateway.py`
  - Keep existing integration coverage.
- Test `tests/test_tool_bridge_replay.py`
  - Add replay-driven regression coverage.

---

## Task 1: Add Sanitized Replay Fixture Format

**Files:**
- Create: `tests/fixtures/tool_bridge_replays/incomplete_bash_operator.json`
- Create: `tests/fixtures/tool_bridge_replays/html_escaped_shell_operator.json`
- Create: `tests/fixtures/tool_bridge_replays/simulated_no_local_tools_denial.json`
- Create: `tests/fixtures/tool_bridge_replays/multiline_agent_summary.json`
- Create: `tests/fixtures/tool_bridge_replays/unknown_task_tool.json`
- Create: `tests/fixtures/tool_bridge_replays/metadata_only_response.json`
- Create: `tests/fixtures/tool_bridge_replays/empty_response.json`
- Create: `webai_gateway/tool_bridge_replay.py`
- Create: `tests/test_tool_bridge_replay.py`

- [x] **Step 1: Create the replay fixture schema**

Each fixture is plain JSON with no secrets:

```json
{
  "id": "incomplete_bash_operator",
  "description": "Web model emits Bash with trailing &&.",
  "protocol": "anthropic_messages",
  "model": "qwen-coder/qwen-coder-plus",
  "tool_bridge_config": {
    "mode": "strict",
    "activationPolicy": "auto",
    "exposurePolicy": "all",
    "maxCallsPerTurn": 4
  },
  "input": {
    "task_text": "审查当前项目代码并制定改进计划",
    "tools": [
      {
        "name": "Bash",
        "description": "Run shell commands.",
        "input_schema": {
          "type": "object",
          "properties": {
            "command": {
              "type": "string"
            }
          },
          "required": [
            "command"
          ]
        }
      }
    ],
    "model_text": "```tool_json\n{\"calls\":[{\"id\":\"call_1\",\"name\":\"Bash\",\"input\":{\"command\":\"git status --short &&\"}}]}\n```"
  },
  "expected": {
    "error": null,
    "tool_calls": [
      {
        "id": "call_1",
        "name": "Bash",
        "input": {
          "command": "git status --short"
        }
      }
    ],
    "warning_contains": null
  }
}
```

- [x] **Step 2: Implement fixture loader**

Create `webai_gateway/tool_bridge_replay.py`:

```python
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
    cases: list[ReplayCase] = []
    for path in sorted(root.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        case_id = str(payload["id"])
        cases.append(ReplayCase(id=case_id, path=path, payload=payload))
    return cases


def run_replay_case(case: ReplayCase) -> dict[str, Any]:
    payload = case.payload
    raw_config = payload.get("tool_bridge_config") or {}
    config = ToolBridgeConfig(
        mode=str(raw_config.get("mode") or "strict"),
        activation_policy=str(raw_config.get("activationPolicy") or "auto"),
        exposure_policy=str(raw_config.get("exposurePolicy") or "all"),
        max_calls_per_turn=int(raw_config.get("maxCallsPerTurn") or 4),
    )
    input_payload = payload["input"]
    context = build_context(input_payload["tools"], config, model=str(payload.get("model") or ""))
    context = prefer_local_tools_for_local_agent_task(
        context,
        [{"role": "user", "content": str(input_payload.get("task_text") or "")}],
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
```

- [x] **Step 3: Add parameterized replay tests**

Create `tests/test_tool_bridge_replay.py`:

```python
from __future__ import annotations

from pathlib import Path

import pytest

from webai_gateway.tool_bridge_replay import ReplayCase, load_replay_cases, run_replay_case


REPLAY_ROOT = Path(__file__).parent / "fixtures" / "tool_bridge_replays"


@pytest.mark.parametrize("case", load_replay_cases(REPLAY_ROOT), ids=lambda case: case.id)
def test_tool_bridge_replay_case(case: ReplayCase) -> None:
    actual = run_replay_case(case)
    expected = case.payload["expected"]
    assert actual["error"] == expected["error"]
    assert actual["tool_calls"] == expected["tool_calls"]
    warning_contains = expected.get("warning_contains")
    if warning_contains:
        assert actual["warning"] and warning_contains in actual["warning"]
```

- [x] **Step 4: Verify the first fixtures fail or pass intentionally**

Run:

```powershell
py -3.11 -m pytest -q tests/test_tool_bridge_replay.py
```

Expected:

```text
7 passed
```

If any fixture fails, do not edit the fixture to match broken behavior. Fix the compiler task that owns that failure class.

---

## Task 2: Turn ToolBridge Into A Deterministic Compiler Pipeline

**Files:**
- Modify: `webai_gateway/tool_bridge.py`
- Test: `tests/test_gateway.py`
- Test: `tests/test_tool_bridge_replay.py`

- [ ] **Step 1: Add compiler phase data**

Add lightweight phase records near `BridgeResult`:

```python
@dataclass
class BridgePhase:
    name: str
    status: str
    detail: str = ""


def _phase(name: str, status: str, detail: str = "") -> BridgePhase:
    return BridgePhase(name=name, status=status, detail=_safe_bridge_detail(detail))
```

Extend `BridgeResult`:

```python
@dataclass
class BridgeResult:
    tool_calls: list[ToolCallDraft]
    error: BridgeError | None = None
    warning: str | None = None
    phases: list[BridgePhase] = field(default_factory=list)
```

- [ ] **Step 2: Split parsing into named phases**

Keep `parse_tool_response(text, context)` as the public entry point. Internally call:

```python
def parse_tool_response(text: str, context: ToolBridgeContext) -> BridgeResult:
    phases: list[BridgePhase] = []
    extracted = _extract_tool_payload(text, context, phases)
    if extracted.error:
        return BridgeResult([], error=extracted.error, warning=extracted.warning, phases=phases)
    drafts = _parse_tool_payload(extracted.payload, context, phases)
    if drafts.error:
        return BridgeResult([], error=drafts.error, warning=drafts.warning, phases=phases)
    normalized = _normalize_tool_call_drafts(drafts.calls, context, phases)
    validated = _validate_tool_call_drafts(normalized, context, phases)
    return BridgeResult(validated.calls, error=validated.error, warning=validated.warning, phases=phases)
```

Do not change the external response format in this task.

- [ ] **Step 3: Preserve existing behavior with focused tests**

Run:

```powershell
py -3.11 -m pytest -q tests/test_gateway.py -k "tool_bridge and not qwen"
```

Expected:

```text
all selected tests pass
```

- [ ] **Step 4: Run replay suite**

Run:

```powershell
py -3.11 -m pytest -q tests/test_tool_bridge_replay.py
```

Expected:

```text
all replay cases pass
```

---

## Task 3: Add Safe Compiler Diagnostics To Admin Events

**Files:**
- Modify: `webai_gateway/app.py`
- Modify: `webai_gateway/openai_api.py`
- Modify: `webai_gateway/anthropic_api.py`
- Test: `tests/test_gateway.py`

- [ ] **Step 1: Write diagnostics test**

Add test in `tests/test_gateway.py`:

```python
def test_tool_bridge_rejection_records_compiler_phases(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=_openai_response(
                '```tool_json\n{"calls":[{"id":"call_1","name":"MissingTool","input":{}}]}\n```'
            ),
            request=request,
        )

    config = GatewayConfig(
        server=ServerConfig(api_key="local-dev-key"),
        upstream=UpstreamConfig(base_url="http://upstream.test/v1", model="web-model"),
        tool_bridge=ToolBridgeConfig(activation_policy="always", exposure_policy="all"),
    )
    client = TestClient(create_app(config=config, http_client=httpx.Client(transport=httpx.MockTransport(handler))))
    response = client.post(
        "/v1/messages",
        headers={**_headers(), "anthropic-version": "2023-06-01"},
        json={
            "model": "web-model",
            "messages": [{"role": "user", "content": "读取项目结构"}],
            "tools": [{"name": "Read", "description": "Read file", "input_schema": {"type": "object"}}],
            "max_tokens": 1024,
        },
    )
    assert response.status_code == 200
    events = client.get("/api/admin/tool-bridge-events", headers=_headers()).json()["events"]
    rejection = [event for event in events if event["kind"] == "tool_bridge_rejection"][-1]
    assert rejection["error"] == "unknown_tool"
    assert "phases" in rejection
    assert all("cookie" not in str(phase).lower() for phase in rejection["phases"])
```

- [ ] **Step 2: Attach phase summaries when recording bridge events**

Add helper in `webai_gateway/app.py`:

```python
def _tool_bridge_phase_fields(result: Any) -> dict[str, Any]:
    phases = getattr(result, "phases", None)
    if not phases:
        return {}
    return {
        "phases": [
            {
                "name": getattr(phase, "name", ""),
                "status": getattr(phase, "status", ""),
                "detail": _diagnostic_text(getattr(phase, "detail", "")),
            }
            for phase in phases
        ][:12]
    }
```

Call this helper from existing `_record_tool_bridge_parse_event` or equivalent bridge event recorders.

- [ ] **Step 3: Verify diagnostics**

Run:

```powershell
py -3.11 -m pytest -q tests/test_gateway.py -k "compiler_phases or request_diagnostics or tool_bridge_rejection"
```

Expected:

```text
all selected tests pass
```

---

## Task 4: Formalize Tool Exposure Profiles

**Files:**
- Modify: `webai_gateway/config.py`
- Modify: `webai_gateway/tool_bridge.py`
- Modify: `config.example.json`
- Test: `tests/test_gateway.py`

- [ ] **Step 1: Add profile configuration**

Add fields to `ToolBridgeConfig`:

```python
tool_profile: str = "auto"
readonly_tool_names: tuple[str, ...] = ()
write_tool_names: tuple[str, ...] = ()
shell_tool_names: tuple[str, ...] = ()
```

Support JSON keys:

```json
{
  "tool_bridge": {
    "toolProfile": "auto",
    "readonlyToolNames": [],
    "writeToolNames": [],
    "shellToolNames": []
  }
}
```

- [ ] **Step 2: Implement profile selection**

Inside `build_context` or the current exposure filter, derive a profile:

```python
def _select_tool_profile(config: ToolBridgeConfig, task_text: str) -> str:
    profile = (config.tool_profile or "auto").strip().lower()
    if profile != "auto":
        return profile
    if _looks_like_plain_qa_task(task_text):
        return "none"
    if _looks_like_readonly_review_task(task_text):
        return "read-only"
    if _task_explicitly_allows_mutation(task_text):
        return "agent"
    return "read-only"
```

Profile behavior:

- `none`: do not inject tool manifest.
- `read-only`: inject Read/Glob/Grep/list/search/get/query style tools; hide Bash/Edit/Write unless explicitly configured.
- `agent`: inject structured Read/Glob/Grep/Edit/Write tools; expose Bash only when downstream registered it and current task explicitly allows shell execution.
- `all`: expose all registered tools for diagnostics and controlled tests only.

- [ ] **Step 3: Add tests for profile decisions**

Add tests:

```python
def test_auto_profile_hides_tools_for_plain_qa() -> None:
    context = build_context([...Read tool...], ToolBridgeConfig(tool_profile="auto"))
    prepared = prepare_openai_messages([{"role": "user", "content": "你是什么模型？"}], context)
    assert "```tool_json" not in prepared[0]["content"]


def test_auto_profile_prefers_readonly_for_review_task() -> None:
    context = build_context([...Bash, Read, Glob tools...], ToolBridgeConfig(tool_profile="auto"))
    context = prefer_local_tools_for_local_agent_task(context, [{"role": "user", "content": "审查当前代码"}])
    names = {tool.name for tool in context.tools}
    assert "Read" in names
    assert "Glob" in names
    assert "Bash" not in names
```

- [ ] **Step 4: Verify**

Run:

```powershell
py -3.11 -m pytest -q tests/test_gateway.py -k "auto_profile or exposure or hides_runtime"
```

Expected:

```text
all selected tests pass
```

---

## Task 5: Harden Prompt Budget And Compaction By Priority

**Files:**
- Modify: `webai_gateway/tool_bridge.py`
- Modify: `webai_gateway/qwen_web.py`
- Modify: `webai_gateway/qwen_coder.py`
- Test: `tests/test_gateway.py`

- [ ] **Step 1: Add priority-band compaction tests**

Add tests proving that compaction keeps the latest user task, tool protocol, allowed tool names, and recent tool results:

```python
def test_prompt_compaction_preserves_protocol_and_latest_task() -> None:
    long_history = [{"role": "user", "content": "old " * 10000}]
    latest = {"role": "user", "content": "审查当前项目结构"}
    context = build_context([...Read tool...], ToolBridgeConfig(tool_prompt_max_chars=2000))
    prepared = prepare_openai_messages([*long_history, latest], context)
    text = "\n".join(str(message.get("content", "")) for message in prepared)
    assert "```tool_json" in text
    assert "Read" in text
    assert "审查当前项目结构" in text
```

- [ ] **Step 2: Implement priority-band compaction**

Compaction order must be:

1. Preserve tool protocol instruction.
2. Preserve full list of real allowed tool names.
3. Preserve latest user task.
4. Preserve most recent tool_result summary.
5. Compress older conversation into bounded recap.
6. Drop low-priority historical prose first.

Add helper:

```python
def _compact_bridge_prompt_parts(parts: list[PromptPart], max_chars: int) -> str:
    required = [part for part in parts if part.priority == "required"]
    recent = [part for part in parts if part.priority == "recent"]
    optional = [part for part in parts if part.priority == "optional"]
    text = _join_parts([*required, *recent, *optional])
    if len(text) <= max_chars:
        return text
    optional_summary = _summarize_optional_parts(optional)
    return _join_parts([*required, *recent, optional_summary])[:max_chars]
```

- [ ] **Step 3: Verify provider prompt diagnostics**

Run:

```powershell
py -3.11 -m pytest -q tests/test_gateway.py -k "prompt_compaction or prompt_max_chars or provider_diagnostic"
```

Expected:

```text
all selected tests pass
```

---

## Task 6: Make Empty And Metadata-Only Provider Responses Non-Silent

**Files:**
- Modify: `webai_gateway/qwen_web.py`
- Modify: `webai_gateway/qwen_coder.py`
- Modify: `webai_gateway/app.py`
- Test: `tests/test_gateway.py`

- [ ] **Step 1: Add tests for empty and metadata-only responses**

Add tests where provider streaming returns:

```text
event: result
data: {"request_id":"abc","usage":{}}
```

and:

```text
data: [DONE]
```

Expected behavior:

- Retry once with a shorter direct-answer prompt if the request has no tools.
- Retry once with a strict tool-only prompt if the request has tools.
- If still empty, return a Chinese diagnostic assistant message and record `metadata_only_response=true` or `empty_provider_response=true`.

- [ ] **Step 2: Standardize provider empty-response diagnostic**

Add shared diagnostic text builder:

```python
def _empty_provider_response_text(route: str, diagnostic: dict[str, Any]) -> str:
    return (
        "上游网页登录模型没有返回可用正文。"
        f" route={route}; "
        f"stream_events={diagnostic.get('stream_events', 0)}; "
        f"output_chars={diagnostic.get('output_chars', 0)}。"
        "请重试一次；如果持续发生，请在管理台查看请求诊断。"
    )
```

- [ ] **Step 3: Verify**

Run:

```powershell
py -3.11 -m pytest -q tests/test_gateway.py -k "metadata_only or empty_response or empty_provider"
```

Expected:

```text
all selected tests pass
```

---

## Task 7: Add End-To-End Client Compatibility Matrix

**Files:**
- Create: `tests/test_client_compat_matrix.py`
- Create: `tests/fixtures/client_compat/*.json`

- [x] **Step 1: Define matrix fixture format**

Create `tests/fixtures/client_compat/claude_code_init.json`:

```json
{
  "id": "claude_code_init",
  "client": "anthropic_messages",
  "model": "qwen-coder/qwen-coder-plus",
  "request": {
    "model": "qwen-coder/qwen-coder-plus",
    "max_tokens": 1024,
    "messages": [
      {
        "role": "user",
        "content": "/init"
      }
    ],
    "tools": [
      {
        "name": "Read",
        "description": "Read files.",
        "input_schema": {
          "type": "object"
        }
      },
      {
        "name": "Glob",
        "description": "Find files.",
        "input_schema": {
          "type": "object"
        }
      },
      {
        "name": "Bash",
        "description": "Run shell commands.",
        "input_schema": {
          "type": "object"
        }
      }
    ]
  },
  "provider_response": "```tool_json\n{\"calls\":[{\"id\":\"call_1\",\"name\":\"Glob\",\"input\":{\"pattern\":\"*.md\"}}]}\n```",
  "expected": {
    "status": 200,
    "stop_reason": "tool_use",
    "tool_names": [
      "Glob"
    ]
  }
}
```

- [x] **Step 2: Implement matrix runner**

Create `tests/test_client_compat_matrix.py`:

```python
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
from fastapi.testclient import TestClient

from webai_gateway.app import create_app
from webai_gateway.config import GatewayConfig, ServerConfig, ToolBridgeConfig, UpstreamConfig


ROOT = Path(__file__).parent / "fixtures" / "client_compat"


def _headers() -> dict[str, str]:
    return {"Authorization": "Bearer local-dev-key"}


def _openai_response(content: str) -> dict[str, Any]:
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "created": 1,
        "model": "web-model",
        "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": content}}],
    }


def test_client_compat_matrix() -> None:
    for path in sorted(ROOT.glob("*.json")):
        case = json.loads(path.read_text(encoding="utf-8"))

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=_openai_response(case["provider_response"]), request=request)

        config = GatewayConfig(
            server=ServerConfig(api_key="local-dev-key"),
            upstream=UpstreamConfig(base_url="http://upstream.test/v1", model="web-model"),
            tool_bridge=ToolBridgeConfig(mode="strict", activation_policy="auto", exposure_policy="all", max_calls_per_turn=4),
        )
        client = TestClient(create_app(config=config, http_client=httpx.Client(transport=httpx.MockTransport(handler))))
        response = client.post(
            "/v1/messages",
            headers={**_headers(), "anthropic-version": "2023-06-01"},
            json=case["request"],
        )
        assert response.status_code == case["expected"]["status"], case["id"]
        body = response.json()
        if "stop_reason" in case["expected"]:
            assert body["stop_reason"] == case["expected"]["stop_reason"], case["id"]
        if "tool_names" in case["expected"]:
            actual_names = [block["name"] for block in body["content"] if block["type"] == "tool_use"]
            assert actual_names == case["expected"]["tool_names"], case["id"]
```

- [x] **Step 3: Add minimum matrix cases**

Create fixtures for:

- `claude_code_plain_qa.json`
- `claude_code_init.json`
- `claude_code_review_readonly.json`
- `claude_code_continue_after_tool_result.json`
- `krisai_plain_qa.json`
- `krisai_tool_request.json`
- `krisai_empty_provider_response.json`
- `qwen_coder_metadata_only.json`
- `qwen_web_unknown_tool_repair.json`
- `qwen_web_deferred_research.json`

- [x] **Step 4: Verify matrix**

Run:

```powershell
py -3.11 -m pytest -q tests/test_client_compat_matrix.py
```

Expected:

```text
all matrix cases pass
```

---

## Task 8: Add Admin Diagnostics For Fast Root Cause Identification

**Files:**
- Modify: `webai_gateway/static/app.js`
- Modify: `webai_gateway/app.py`
- Test: `tests/test_gateway.py`

- [x] **Step 1: Add diagnostic fields**

Ensure `/api/admin/request-diagnostics` includes:

```json
{
  "endpoint": "/v1/messages",
  "route": "qwen-coder",
  "model": "qwen-coder/qwen-coder-plus",
  "bridge": true,
  "providerPromptChars": 32000,
  "providerPromptMaxChars": 32000,
  "providerPromptCompacted": false,
  "responseContentChars": 0,
  "responseToolUseCount": 0,
  "toolBridgeError": "unknown_tool",
  "toolBridgePhases": [
    {
      "name": "extract",
      "status": "ok"
    }
  ],
  "safeResponsePreview": "..."
}
```

- [x] **Step 2: Render a Chinese diagnostics summary**

In `webai_gateway/static/app.js`, show:

```javascript
function renderToolBridgeSummary(event) {
  const parts = []
  if (event.toolBridgeError) parts.push(`工具桥错误：${event.toolBridgeError}`)
  if (event.providerPromptCompacted) parts.push('Prompt 已压缩')
  if (event.responseContentChars === 0) parts.push('上游返回正文为空')
  if (event.route) parts.push(`路由：${event.route}`)
  return parts.length ? parts.join('；') : '未发现工具桥异常'
}
```

- [x] **Step 3: Verify diagnostics stay redacted**

Run:

```powershell
py -3.11 -m pytest -q tests/test_gateway.py -k "diagnostics_redacts or request_diagnostics"
```

Expected:

```text
all selected tests pass
```

---

## Task 9: Run Full Verification And Real Smoke Tests

**Files:**
- Modify only if verification exposes a bug in earlier tasks.

- [ ] **Step 1: Run full backend test suite**

Run:

```powershell
py -3.11 -m pytest -q
```

Expected:

```text
all tests pass
```

- [ ] **Step 2: Run frontend build**

Run:

```powershell
pnpm build
```

in:

```text
E:\ProjectX\webai-gateway\webui
```

Expected:

```text
vite build exits with code 0
```

Vite chunk size warnings are acceptable unless the build exits non-zero.

- [ ] **Step 3: Restart Gateway**

Run:

```powershell
$listeners = Get-NetTCPConnection -LocalPort 8610 -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique
foreach ($ownerPid in $listeners) {
  if ($ownerPid -and $ownerPid -ne 0) {
    Stop-Process -Id $ownerPid -Force
  }
}
Start-Sleep -Seconds 2
$out = Join-Path (Get-Location) 'gateway.current.out.log'
$err = Join-Path (Get-Location) 'gateway.current.err.log'
Start-Process -FilePath 'py' -ArgumentList @('-3.11','-m','webai_gateway') -WorkingDirectory (Get-Location) -RedirectStandardOutput $out -RedirectStandardError $err -WindowStyle Hidden
Start-Sleep -Seconds 4
Invoke-RestMethod -Uri 'http://127.0.0.1:8610/health' -Headers @{Authorization='Bearer local-dev-key'} -TimeoutSec 10
```

Expected:

```text
health response ok=true
```

- [ ] **Step 4: Run mocked Claude Code smoke**

Send Anthropic Messages payload to `/v1/messages` with `Read`, `Glob`, and `Bash` tools. Mock or configure provider so the first response asks for `Glob`. Expected:

```text
HTTP 200
stop_reason=tool_use
content contains one tool_use block
tool name is Glob
```

- [ ] **Step 5: Run mocked KrisAI smoke**

Send OpenAI Chat Completions payload to `/v1/chat/completions` with `tools`. Mock provider response with a fenced `tool_json`. Expected:

```text
HTTP 200
choices[0].finish_reason=tool_calls
choices[0].message.tool_calls is not empty
```

- [ ] **Step 6: Run one live no-secret smoke per enabled provider**

Use only harmless prompts:

```text
请用一句中文回答：你收到消息了吗？
```

Expected:

```text
non-empty Chinese text response
request diagnostics show the intended route and model
no secret appears in logs
```

Do not claim provider-specific agent support based on plain chat only. Tool support requires the mocked and live tool-call smoke to pass.

---

## Definition Of Done

The work is complete only when all of these are true:

- `py -3.11 -m pytest -q` passes.
- `pnpm build` in `E:\ProjectX\webai-gateway\webui` passes.
- Replay suite covers at least 10 real failure families from Claude Code and KrisAI.
- Compatibility matrix covers Anthropic Messages and OpenAI Chat Completions.
- Gateway diagnostics can identify whether a failure is provider timeout, empty provider output, prompt compaction, unknown tool, invalid shell syntax, unsafe shell policy, or downstream execution failure.
- No Gateway code executes local tools.
- No compatibility branch is named after Claude Code, KrisAI, OpenClaw, or Hermes as business logic.
- No logs, fixtures, tests, docs, or UI output contain secrets.
- Manual smoke with the intended model shows non-empty response and correct tool call format.

---

## Self-Review

**Spec coverage:** The plan covers repeated invalid tool calls, empty responses, metadata-only provider responses, prompt length pressure, tool exposure, diagnostics, and multi-client compatibility without adding client-specific runtime branches.

**Placeholder scan:** The plan contains concrete files, commands, fixture shapes, and expected outputs. It avoids deferred implementation placeholders.

**Type consistency:** New helper names are consistent across tasks: `ReplayCase`, `load_replay_cases`, `run_replay_case`, `BridgePhase`, and `ToolBridgeConfig` profile fields.

**Risk note:** The existing `webai_gateway/tool_bridge.py` is large. This plan avoids moving the whole file at once. It only adds a replay harness and incremental internal phase boundaries first; deeper module splitting should wait until the replay suite is green.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-29-systemic-agent-compatibility.md`.

Two execution options:

1. **Subagent-Driven recommended:** one worker builds replay fixtures, one worker implements compiler phases, one worker implements diagnostics and matrix tests. Review after each task.
2. **Inline Execution:** execute tasks sequentially in this session with verification checkpoints after each task.
