# Strict Final Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在活动本地 agent 工具循环中阻止未证明为最终答案的纯文本 `end_turn`，减少网页模型用不同说法逃逸工具协议。

**Architecture:** 在 `webai_gateway/tool_bridge.py` 的 no-candidate plain-text 分支增加 Strict Final Gate。更具体的已有错误先返回，最后由通用 gate 兜底；配置层新增 `semanticFinalJudge` 字段用于后续 shadow/enforce 扩展。

**Tech Stack:** Python dataclasses, FastAPI test client, pytest, existing ToolBridge replay suite.

---

### Task 1: 配置预留 semanticFinalJudge

**Files:**
- Modify: `webai_gateway/config.py`
- Modify: `config.example.json`
- Test: `tests/test_gateway.py`

- [ ] **Step 1: Write failing config test**

Add a test asserting `ToolBridgeConfig.semantic_final_judge` defaults to `off`, loads camelCase config, and appears in public/admin config.

- [ ] **Step 2: Run targeted test and verify fail**

Run:

```powershell
python -m pytest tests/test_gateway.py::test_tool_bridge_config_exposes_semantic_final_judge -q
```

Expected: fails because the field is missing.

- [ ] **Step 3: Implement config field**

Add `semantic_final_judge: str = "off"` to `ToolBridgeConfig`; load `semanticFinalJudge` / `semantic_final_judge`; include in `config_to_public`, `config_to_admin`, and `update_config`; add `"semanticFinalJudge": "off"` to `config.example.json`.

- [ ] **Step 4: Verify target passes**

Run the same targeted pytest command. Expected: pass.

### Task 2: Strict Final Gate Parser

**Files:**
- Modify: `webai_gateway/tool_bridge.py`
- Test: `tests/test_gateway.py`

- [ ] **Step 1: Write failing parser tests**

Add tests for:

- inline fix step without `tool_json` returns `incomplete_fix_stub_without_tool_call`;
- codebase overview / different file path text returns `deferred_tool_action_without_call`;
- generic short unproven next-action text returns `unproven_final_answer_without_tool_call`;
- complete final review summary remains allowed.

- [ ] **Step 2: Run targeted parser tests and verify fail**

Run:

```powershell
python -m pytest tests/test_gateway.py::test_tool_bridge_rejects_inline_fix_step_without_tool_call tests/test_gateway.py::test_tool_bridge_rejects_codebase_overview_intent_without_tool_call tests/test_gateway.py::test_tool_bridge_rejects_unproven_final_answer_without_tool_call tests/test_gateway.py::test_tool_bridge_allows_complete_review_summary_without_tool_call -q
```

Expected: new rejection tests fail before implementation; allowed-summary test should pass or be fixed if the new gate is too broad.

- [ ] **Step 3: Implement minimal gate helpers**

Add local helpers:

- `_is_unproven_final_answer_without_tool_call(text, context)`
- `_looks_like_complete_final_answer(text, context)`
- `_UNPROVEN_FINAL_ACTION_RE`
- `_FINAL_ANSWER_MARKER_RE`

Call the gate after existing specific no-candidate guards and before final plain-text return.

- [ ] **Step 4: Verify target passes**

Run the targeted parser tests. Expected: pass.

### Task 3: Integration Repair Loop

**Files:**
- Modify: `tests/test_gateway.py`
- Modify: `webai_gateway/tool_bridge.py` only if integration exposes missing repair text

- [ ] **Step 1: Write failing `/v1/messages` repair test**

Use a fake qwen-coder client that first returns `Need a better project map before proceeding. Continue with another file path.` and then returns a valid `Glob` `tool_json`.

- [ ] **Step 2: Run targeted integration test and verify fail**

Run:

```powershell
python -m pytest tests/test_gateway.py::test_qwen_coder_repairs_unproven_final_answer_without_tool_call -q
```

Expected: fails before gate implementation or if repair prompt does not carry the error kind.

- [ ] **Step 3: Ensure repair prompt includes `unproven_final_answer_without_tool_call`**

Reuse existing `build_repair_messages`; no custom prompt is needed unless the test proves otherwise.

- [ ] **Step 4: Verify target passes**

Run the targeted integration test. Expected: pass.

### Task 4: Replay And Lessons

**Files:**
- Create: `tests/fixtures/tool_bridge_replays/inline_fix_step_without_tool_json.json`
- Create: `tests/fixtures/tool_bridge_replays/codebase_overview_intent_without_tool_json.json`
- Create: `tests/fixtures/tool_bridge_replays/unproven_final_answer_without_tool_json.json`
- Modify: `.learnings/ERRORS.md`

- [ ] **Step 1: Add replay fixtures**

Each fixture should include the original model text, active local-agent messages, read-like tools, and expected error.

- [ ] **Step 2: Append learning**

Record the architectural lesson: stop enumerating every wording; require final-answer proof in active tool loops.

- [ ] **Step 3: Run replay report**

Run:

```powershell
python -m webai_gateway.auto_research report --fixtures tests\fixtures\tool_bridge_replays
```

Expected: all fixtures pass and total count increases.

### Task 5: Full Verification And Restart

**Files:**
- No new files unless tests reveal a gap.

- [ ] **Step 1: Run full backend tests**

Run:

```powershell
python -m pytest -q
```

Expected: all tests pass.

- [ ] **Step 2: Restart Gateway**

Stop existing `python -m webai_gateway`, start a fresh hidden process from `E:\ProjectX\webai-gateway`.

- [ ] **Step 3: Verify health**

Run:

```powershell
Invoke-RestMethod http://127.0.0.1:8610/health
```

Expected:

- `ok=true`
- `runtime.sourceFresh=true`
- `runtime.sourceStale=false`

---

## Self-Review

- Spec coverage: covers final gate, config prewire, replay, verification, restart.
- Placeholder scan: no TBD/TODO placeholders.
- Type consistency: config uses `semantic_final_judge` internally and `semanticFinalJudge` externally.
