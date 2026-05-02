# Tool Policy Bridge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make WebAI Gateway treat Claude Code / KrisAI tool calls as protocol-level operations with task-stage policy, so review/planning tasks cannot drift into mutating local execution.

**Architecture:** Keep Gateway as a protocol adapter, not an agent runtime. Add policy checks inside `ToolBridgeV2` before returning tool calls to downstream clients: derive the original human task, classify task stage, classify shell command capability, and stop retries for policy-denied calls.

**Tech Stack:** Python, FastAPI, pytest, OpenAI/Anthropic-compatible payload conversion.

---

### Task 1: Preserve Human Task Intent Across Tool Loops

**Files:**
- Modify: `webai_gateway/tool_bridge.py`
- Test: `tests/test_gateway.py`

- [x] **Step 1: Write failing tests**

Add tests where Anthropic-style tool results appear as later `role=user` messages, but task intent must still come from the original human prompt:

```python
def test_tool_bridge_uses_original_human_prompt_after_tool_result_for_review_policy() -> None:
    context = build_context([...Bash tool...], ToolBridgeConfig(exposure_policy="all"))
    messages = [
        {"role": "user", "content": "审查下代码并且制定改进计划"},
        {"role": "assistant", "content": [{"type": "tool_use", "id": "call_1", "name": "Bash", "input": {"command": "git status --short"}}]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "call_1", "content": "On branch security/fix-secrets-leak"}]},
    ]
    context = prefer_local_tools_for_local_agent_task(context, messages)
    result = parse_tool_response('```tool_json\n{"calls":[{"id":"call_2","name":"Bash","input":{"command":"git checkout -b security/hotfix"}}]}\n```', context)
    assert result.error.kind == "unsafe_review_shell_command"
```

- [x] **Step 2: Implement original-human-message extraction**

Add helper logic that skips tool-result messages when finding task intent:

```python
def _latest_human_user_text(messages: Any) -> str:
    for message in reversed(messages or []):
        if message.get("role") != "user":
            continue
        if _message_is_tool_result(message):
            continue
        text = _content_to_text(message.get("content"))
        if text.strip():
            return text
    return ""
```

### Task 2: Add Task-Stage Policy To Shell Calls

**Files:**
- Modify: `webai_gateway/tool_bridge.py`
- Test: `tests/test_gateway.py`

- [x] **Step 1: Write command matrix tests**

For `审查代码并制定改进计划`, block:

```text
git checkout -b security/hotfix-secrets-rotation
pip install pytest pytest-cov && pytest --cov=src
python -c "..." > .env.example
git secrets --register-aws
python utils/rotate_secrets.py --all
git add . && git commit -m "..."
```

Allow:

```text
git status --short
git log --oneline -n 5
git grep -i "secret" -- "*.py"
ls -la E:/ProjectX/mindcraft
```

- [x] **Step 2: Implement shell capability classification**

Add a command policy check that classifies shell segments before returning tool calls:

```python
def _shell_command_policy_error(command: str, context: ToolBridgeContext) -> BridgeError | None:
    if _task_stage(context.task_text) == "review":
        if _shell_segment_has_mutation(words) or _shell_segment_is_broad_test(words):
            return BridgeError("unsafe_review_shell_command", "...", repairable=False)
```

### Task 3: Stop Retrying Policy Denials

**Files:**
- Modify: `webai_gateway/tool_bridge.py`
- Modify: `webai_gateway/app.py` if needed
- Test: `tests/test_gateway.py`

- [x] **Step 1: Write failing retry test**

Simulate a model that first asks for `git checkout -b` in a review task. The Gateway must return a normal assistant diagnostic and must not call upstream repair.

- [x] **Step 2: Mark policy denials non-repairable**

For `unsafe_review_shell_command`, use `repairable=False` and a Chinese diagnostic. Do not send repair prompts that ask the model to call another tool.

### Task 4: Verify

**Files:**
- Test: all backend tests

- [x] **Step 1: Run focused tests**

Run:

```powershell
py -3.11 -m pytest tests/test_gateway.py -q -k "review_policy or readonly_review or mutating_shell_pipeline"
```

- [x] **Step 2: Run full backend suite**

Run:

```powershell
py -3.11 -m pytest -q
```

- [x] **Step 3: Restart Gateway and verify health**

Run:

```powershell
py -3.11 -m webai_gateway
Invoke-WebRequest http://127.0.0.1:8610/health
```

---

## Completion Notes

- Implemented original human task extraction that ignores later `tool_result` messages.
- Marked read-only review policy denials as non-repairable so Gateway does not ask the model to retry into another invalid tool call.
- Added qwen-coder `/v1/messages` command matrix tests for common Claude Code Bash variants.
- Preserved ToolBridge diagnostic headers when direct providers are converted through Anthropic `/v1/messages`.
- Verified with `py -3.11 -m pytest -q` and a live local qwen-coder `/v1/messages` smoke request.
