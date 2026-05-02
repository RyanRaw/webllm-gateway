# Tool Bridge Controller Full Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn WebAI Gateway's prompt ToolBridge from a collection of parse guards into a protocol controller that converges through explicit states, retry budgets, evidence-aware finalization, and measurable failure-sample feedback.

**Architecture:** Keep Gateway as a protocol adapter only: it still never executes local tools or downstream permissions. Add a controller module that classifies model output into `TOOL_CALL`, `FINAL`, `ASK_USER`, or `RETRY`, then let existing OpenAI/Anthropic adapters render that state. Keep deterministic validation as the safety boundary; optional semantic judging starts as shadow telemetry and cannot override hard safety rules.

**Tech Stack:** Python dataclasses/enums, FastAPI, pytest, existing `ToolBridgeContext`, replay fixtures, client compatibility matrix, static admin UI.

---

## Current Gap Summary

Already landed:

- Prompt ToolBridge parsing and strict final gate for many plain-text escapes.
- Replay corpus and `auto_research report`.
- Client compatibility matrix for Anthropic Messages and OpenAI Chat Completions.
- Basic admin diagnostics and auto-research dashboard.
- Phase 1 controller stopgaps: recoverable invalid shell artifacts and no-tools local denial detection.

Not fully landed:

- No explicit controller state machine. `_parse_bridge_chat_data` still branches through ad hoc retry paths.
- No centralized retry budget or terminal-state policy.
- No evidence ledger proving a final answer is allowed for local-agent work.
- Unsafe shell / permission-required paths do not consistently become `AskUserQuestion`.
- `semanticFinalJudge` is config/UI only; no shadow classification or telemetry exists.
- Auto-research is offline report/collect only; no live failure mining, taxonomy, trend, or "fixed vs new" view.
- Client compatibility fixtures do not cover the new state-machine transitions.

---

### Task 1: Introduce Controller State Types

**Files:**
- Create: `webai_gateway/tool_controller.py`
- Modify: `webai_gateway/openai_api.py`
- Test: `tests/test_gateway.py`

- [ ] **Step 1: Write failing state classification tests**

Add tests for a pure function `classify_bridge_result(result, context, retry_state)`:

```python
def test_tool_controller_classifies_tool_calls_as_tool_call() -> None:
    result = BridgeResult(content="", tool_calls=[ToolCallDraft(id="call_1", name="Read", input={"file_path": "README.md"})])
    decision = classify_bridge_result(result, _controller_context_with_read(), RetryState())
    assert decision.state == "TOOL_CALL"
```

```python
def test_tool_controller_classifies_repairable_error_as_retry() -> None:
    result = BridgeResult(
        content="bad",
        tool_calls=[],
        error=BridgeError("tool_denial_without_call", "denied", repairable=True),
        raw_content="bad",
    )
    decision = classify_bridge_result(result, _controller_context_with_read(), RetryState())
    assert decision.state == "RETRY"
    assert decision.retry_kind == "repair"
```

- [ ] **Step 2: Run targeted tests**

Run:

```powershell
python -m pytest -q tests/test_gateway.py::test_tool_controller_classifies_tool_calls_as_tool_call tests/test_gateway.py::test_tool_controller_classifies_repairable_error_as_retry
```

Expected before implementation: import or symbol failure.

- [ ] **Step 3: Implement state dataclasses**

Create:

```python
@dataclass(frozen=True)
class RetryState:
    repair_attempts: int = 0
    recovery_attempts: int = 0
    ask_user_attempts: int = 0

@dataclass(frozen=True)
class ControllerDecision:
    state: Literal["TOOL_CALL", "FINAL", "ASK_USER", "RETRY"]
    retry_kind: str = ""
    reason: str = ""
    bridge_result: BridgeResult | None = None
```

Implement `classify_bridge_result` with no side effects.

- [ ] **Step 4: Verify targeted tests pass**

Run the targeted tests again. Expected: pass.

### Task 2: Centralize Retry Budget And Terminal Policy

**Files:**
- Modify: `webai_gateway/tool_controller.py`
- Modify: `webai_gateway/app.py`
- Test: `tests/test_gateway.py`

- [ ] **Step 1: Write failing retry budget tests**

Add tests:

```python
def test_tool_controller_stops_after_repair_budget() -> None:
    result = BridgeResult(
        content="bad",
        tool_calls=[],
        error=BridgeError("malformed_json", "bad json", repairable=True),
        raw_content="bad",
    )
    decision = classify_bridge_result(result, _controller_context_with_read(), RetryState(repair_attempts=1))
    assert decision.state == "FINAL"
    assert decision.reason == "retry_budget_exhausted"
```

```python
def test_tool_controller_allows_first_repair_retry() -> None:
    result = BridgeResult(
        content="bad",
        tool_calls=[],
        error=BridgeError("malformed_json", "bad json", repairable=True),
        raw_content="bad",
    )
    decision = classify_bridge_result(result, _controller_context_with_read(), RetryState(repair_attempts=0))
    assert decision.state == "RETRY"
```

- [ ] **Step 2: Refactor `_parse_bridge_chat_data` to use the controller**

Keep existing retry payload builders. Replace the top-level if/elif chain with a loop:

1. Parse upstream response into `BridgeResult`.
2. Ask controller for a decision.
3. If `TOOL_CALL` or `FINAL`, return.
4. If `RETRY`, build the existing retry payload matching `retry_kind`, call upstream once, update `RetryState`.
5. If budget exhausted, render the safe diagnostic as final text with `x-webai-tool-bridge-error`.

- [ ] **Step 3: Preserve existing diagnostic events**

Keep event kinds:

- `tool_bridge_retry`
- `tool_bridge_rejection`
- `completion_response`

Add fields when available:

- `toolBridgeControllerState`
- `toolBridgeControllerReason`
- `toolBridgeRetryBudget`

- [ ] **Step 4: Verify existing retry tests**

Run:

```powershell
python -m pytest -q tests/test_gateway.py -k "repairs or recovers or retry or tool_bridge_error"
```

Expected: pass.

### Task 3: Evidence Ledger For Final Answers

**Files:**
- Modify: `webai_gateway/tool_controller.py`
- Modify: `webai_gateway/tool_bridge.py`
- Test: `tests/test_gateway.py`
- Create fixtures under: `tests/fixtures/tool_bridge_replays/`

- [ ] **Step 1: Write failing evidence tests**

Add tests:

```python
def test_controller_rejects_final_without_read_evidence_for_local_review() -> None:
    context = _controller_context_with_read(task_text="Review this local project.")
    result = BridgeResult(content="Review complete. No issues found.", tool_calls=[], raw_content="Review complete. No issues found.")
    decision = classify_bridge_result(result, context, RetryState())
    assert decision.state == "RETRY"
    assert decision.reason == "insufficient_final_evidence"
```

```python
def test_controller_allows_final_after_read_evidence_for_readonly_review() -> None:
    context = _controller_context_with_read(
        task_text="Review this local project.",
        recent_tool_call_names=("Glob", "Read", "Grep"),
    )
    result = BridgeResult(content="Review summary: no critical issues were found in inspected files.", tool_calls=[], raw_content="Review summary: no critical issues were found in inspected files.")
    decision = classify_bridge_result(result, context, RetryState())
    assert decision.state == "FINAL"
```

- [ ] **Step 2: Implement evidence extraction**

Add:

```python
@dataclass(frozen=True)
class EvidenceLedger:
    has_discovery: bool
    has_file_read: bool
    has_search: bool
    has_mutation: bool
    has_verification: bool
```

Build it from `ToolBridgeContext.recent_tool_call_names` and summaries. Do not inspect file contents or execute tools.

- [ ] **Step 3: Add task-specific final requirements**

Rules:

- Local review/planning final requires discovery plus at least one read/search signal.
- Local mutation final requires mutation signal and either verification signal or explicit "not run" statement.
- Pure Q&A without tool loop remains unaffected.

- [ ] **Step 4: Add replay fixtures**

Create:

- `local_review_final_without_evidence.json`
- `local_review_final_after_evidence.json`
- `mutation_final_without_verification.json`
- `mutation_final_with_not_run_verification_note.json`

- [ ] **Step 5: Verify replay and targeted tests**

Run:

```powershell
python -m webai_gateway.auto_research report --fixtures tests\fixtures\tool_bridge_replays
python -m pytest -q tests/test_gateway.py -k "evidence or final"
```

Expected: pass.

### Task 4: AskUserQuestion For Permission-Boundary Cases

**Files:**
- Modify: `webai_gateway/tool_controller.py`
- Modify: `webai_gateway/tool_bridge.py`
- Test: `tests/test_gateway.py`
- Add client compatibility fixtures.

- [ ] **Step 1: Write failing AskUserQuestion tests**

Cases:

```python
def test_unsafe_shell_with_ask_user_available_returns_ask_user() -> None:
    context = _controller_context_with_tools(["AskUserQuestion", "Read", "Bash"])
    result = BridgeResult(
        content="",
        tool_calls=[],
        error=BridgeError("unsafe_local_shell_command", "needs shell confirmation", repairable=True),
        raw_content="```tool_json\n{\"calls\":[{\"name\":\"Bash\",\"input\":{\"command\":\"pip install -r requirements.txt\"}}]}\n```",
    )
    decision = classify_bridge_result(result, context, RetryState())
    assert decision.state == "ASK_USER"
```

- [ ] **Step 2: Implement virtual AskUserQuestion call builder**

When controller chooses `ASK_USER`, render one downstream tool call:

```json
{
  "name": "AskUserQuestion",
  "input": {
    "question": "上游模型请求执行需要用户确认的本地命令：pip install -r requirements.txt。是否允许？",
    "options": ["允许本次执行", "改用只读检查", "取消"]
  }
}
```

No local execution happens in Gateway.

- [ ] **Step 3: Preserve hard denials when AskUserQuestion is unavailable**

If no compatible ask-user tool exists, continue returning safe diagnostic text.

- [ ] **Step 4: Add compatibility fixtures**

Add OpenAI and Anthropic fixtures for:

- unsafe shell with AskUserQuestion available -> tool call
- unsafe shell without AskUserQuestion -> safe diagnostic

Run:

```powershell
python -m pytest -q tests/test_client_compat_matrix.py
```

Expected: pass.

### Task 5: Semantic Judge Shadow Mode

**Files:**
- Create: `webai_gateway/semantic_judge.py`
- Modify: `webai_gateway/config.py`
- Modify: `webai_gateway/app.py`
- Modify: `webai_gateway/static/app.js`
- Modify: `webai_gateway/static/index.html`
- Test: `tests/test_gateway.py`

- [ ] **Step 1: Write failing shadow metadata tests**

Add:

```python
def test_semantic_final_judge_shadow_records_metadata_without_enforcing() -> None:
    config = GatewayConfig(
        server=ServerConfig(api_key="local-dev-key"),
        tool_bridge=ToolBridgeConfig(semantic_final_judge="shadow"),
    )
    # Response should remain unchanged, diagnostics should contain judge fields.
```

Expected fields:

- `semanticFinalJudgeMode`
- `semanticFinalJudgeVerdict`
- `semanticFinalJudgeConfidence`
- `semanticFinalJudgeReason`

- [ ] **Step 2: Implement deterministic shadow classifier**

Start with a local classifier using existing final-action and denial signals. Do not call an upstream model in this task. It returns:

```python
SemanticJudgeResult(verdict="allow" | "retry" | "ask_user", confidence=0.0-1.0, reason="...")
```

- [ ] **Step 3: Wire diagnostics only**

In `shadow`, record fields but never override controller decision.

In `off`, do nothing.

Keep `enforce` disabled unless a later task explicitly implements and tests it.

- [ ] **Step 4: Show shadow fields in admin diagnostics**

Update the static diagnostics renderer to show judge verdict and confidence when present.

- [ ] **Step 5: Verify**

Run:

```powershell
python -m pytest -q tests/test_gateway.py -k "semantic_final_judge or diagnostics"
```

Expected: pass.

### Task 6: Live Auto-Research Failure Mining

**Files:**
- Modify: `webai_gateway/auto_research.py`
- Modify: `webai_gateway/app.py`
- Modify: `webai_gateway/static/app.js`
- Test: `tests/test_auto_research.py`

- [ ] **Step 1: Write failing taxonomy tests**

Add tests for:

- grouping fixture failures by `error`
- counting new vs known fixture IDs
- exposing latest failure samples without secrets

- [ ] **Step 2: Add taxonomy report**

Extend `build_auto_research_status` with:

```json
{
  "taxonomy": {
    "invalid_shell_command_artifact": 4,
    "tool_denial_without_call": 2
  },
  "recentFailures": [],
  "knownFixtureIds": []
}
```

- [ ] **Step 3: Add live diagnostics mining endpoint**

Add read-only endpoint:

```text
GET /api/admin/auto-research/candidates
```

It scans in-memory request diagnostics for recent:

- `toolBridgeError`
- `responseToolCallCount=0` in active bridge loops
- no-tools denial text

It does not write files.

- [ ] **Step 4: Add UI cards**

Show:

- replay pass rate
- failure taxonomy
- recent candidates
- copyable collect/report commands

- [ ] **Step 5: Verify**

Run:

```powershell
python -m pytest -q tests/test_auto_research.py tests/test_gateway.py -k "auto_research or diagnostics"
```

Expected: pass.

### Task 7: State-Machine Client Compatibility Matrix

**Files:**
- Add fixtures under: `tests/fixtures/client_compat/`
- Modify: `tests/test_client_compat_matrix.py` only if fixture schema needs expected diagnostics.

- [ ] **Step 1: Add fixtures for all controller states**

Required fixture IDs:

- `openai_controller_tool_call`
- `anthropic_controller_tool_call`
- `openai_controller_repair_then_tool_call`
- `anthropic_controller_repair_then_tool_call`
- `openai_controller_ask_user`
- `anthropic_controller_ask_user`
- `openai_controller_final_with_evidence`
- `anthropic_controller_final_with_evidence`
- `openai_controller_safe_diagnostic_after_budget`
- `anthropic_controller_safe_diagnostic_after_budget`

- [ ] **Step 2: Run compatibility matrix**

Run:

```powershell
python -m pytest -q tests/test_client_compat_matrix.py
```

Expected: pass.

### Task 8: Verification, Restart, And Execution Rule Update

**Files:**
- Modify: `AGENTS.md`
- Modify: `.learnings/ERRORS.md`

- [ ] **Step 1: Update execution rule**

Add or confirm:

- After any Gateway code/config/script/key doc change, run targeted tests, replay report, full pytest.
- Restart Gateway.
- Report `/health` with `ok`, `runtime.sourceFresh`, `runtime.sourceStale`, PID.

- [ ] **Step 2: Record architecture lesson**

Append ERR entry: "ToolBridge failures must be controller states, not direct text responses."

---

## Completion Notes

**2026-05-01 落地结果：** 已完成本计划的主要产品闭环：显式 controller 状态、retry budget 诊断、evidence-aware final gate、`AskUserQuestion` 权限边界、semantic judge shadow telemetry、auto-research live candidates、管理台展示、OpenAI/Anthropic state-machine compatibility matrix。

**验证结果：**

- `python -m webai_gateway.auto_research report --fixtures tests\fixtures\tool_bridge_replays`：50/50 通过。
- `python -m pytest -q tests/test_client_compat_matrix.py`：21 个矩阵测试通过，覆盖 20 个 fixtures，其中 10 个为 `*_controller_*` 状态机 fixtures。
- `python -m pytest -q`：413 passed。

**实现说明：** `_parse_bridge_chat_data` 当前以 controller decision hook 接入现有 retry payload builders，保留原有诊断事件和恢复分支，避免一次性大重构破坏稳定路径。后续如果继续清理内部结构，可以把这些分支机械收敛为单个 loop，但当前用户可见协议行为和回归覆盖已经落地。

- [ ] **Step 3: Full verification**

Run:

```powershell
python -m webai_gateway.auto_research report --fixtures tests\fixtures\tool_bridge_replays
python -m pytest -q
```

Expected:

- replay pass rate 100%
- full pytest pass

- [ ] **Step 4: Restart service and verify health**

Restart `python -m webai_gateway`, then run:

```powershell
Invoke-RestMethod http://127.0.0.1:8610/health
```

Expected:

- `ok=true`
- `runtime.sourceFresh=true`
- `runtime.sourceStale=false`

---

## Self-Review

- Spec coverage: covers state machine, retry policy, evidence gate, ask-user boundary, semantic judge shadow, auto-research telemetry, compatibility matrix, verification/restart.
- Placeholder scan: no TBD/TODO placeholders.
- Type consistency: controller states are `TOOL_CALL`, `FINAL`, `ASK_USER`, `RETRY`; config remains `semantic_final_judge` internally and `semanticFinalJudge` externally.
- Scope check: this is larger than Phase 1 but still one subsystem: ToolBridge protocol control. It should be implemented task-by-task with verification after each task.
