# Tool Bridge Controller Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent Claude Code tool tasks from terminating when the upstream web model emits a recoverable invalid tool artifact or a no-tool "I cannot access files" denial.

**Architecture:** Keep Gateway as a protocol adapter only. Add a small controller layer around existing parsing: recoverable invalid tool artifacts enter a retry path, and no-tools provider denials are forced through the existing tool bridge when downstream tools exist.

**Tech Stack:** FastAPI, pytest, existing `ToolBridgeConfig`, `BridgeResult`, `parse_chat_response`, and direct Qwen Coder provider test harness.

---

### Task 1: Make Invalid Shell Artifacts Recoverable

**Files:**
- Modify: `webai_gateway/tool_bridge.py`
- Modify: `tests/test_gateway.py`
- Create: `tests/fixtures/tool_bridge_replays/package_requirement_text_as_bash_recoverable.json`

- [x] **Step 1: Write failing unit test**

Add a test that parses `Bash({"command":"python-dotenv>=1.0.0 && pytest>=7.0.0"})` and expects `invalid_shell_command_artifact` with `repairable=True`.

- [x] **Step 2: Run targeted test**

Run: `python -m pytest -q tests/test_gateway.py::test_tool_bridge_marks_package_requirement_bash_artifact_repairable`

Expected before implementation: fail because the error is not repairable.

- [x] **Step 3: Implement minimal fix**

In `_invalid_shell_command_artifact_error`, change package-requirement, source-code invocation, and placeholder `git clone` artifact errors to `repairable=True`. Keep unsafe/destructive shell errors non-repairable.

- [x] **Step 4: Verify retry path**

Add a provider test where first response is a bad Bash artifact and second response is a valid `Read`/`Glob`/`Edit` `tool_json`. Assert two upstream calls and final Anthropic `tool_use`.

### Task 2: Route No-Tool Local Denials Through ToolBridge

**Files:**
- Modify: `webai_gateway/openai_api.py`
- Modify: `tests/test_gateway.py`

- [x] **Step 1: Write failing provider test**

Add a Qwen Coder test where the request has local tools, the initial upstream payload has no native tools after prompt-bridging, and the model replies "无法直接访问项目文件". Assert Gateway retries and returns a real downstream `Read` tool call.

- [x] **Step 2: Implement bridge parse for no-tools denial**

In `parse_chat_response`, when `bridge=False` but `bridge_context.enabled` and `bridge_context.allowed_names` are present, run `parse_tool_response` in denial-detection mode for content that claims missing filesystem/tool access. If it returns a repairable tool error, surface that `BridgeResult` to `_parse_bridge_chat_data` so existing retry/recovery handles it.

- [x] **Step 3: Avoid broad false positives**

Only activate this path when downstream tools exist and the text matches existing tool denial detection. Do not apply to normal non-tool chat or native web search.

### Task 3: Verify And Restart

**Files:**
- Modify: `.learnings/ERRORS.md`

- [x] **Step 1: Record the lesson**

Add an ERR entry explaining that recoverable invalid tool artifacts and no-tool local denials must go to retry/ask-user, never direct `end_turn`.

- [x] **Step 2: Run verification**

Run:

```powershell
python -m webai_gateway.auto_research report --fixtures tests\fixtures\tool_bridge_replays
python -m pytest -q
```

Expected: all replay fixtures and tests pass.

- [x] **Step 3: Restart Gateway**

Restart `python -m webai_gateway`, then verify `/health` reports `ok=true`, `runtime.sourceFresh=true`, and `runtime.sourceStale=false`.
