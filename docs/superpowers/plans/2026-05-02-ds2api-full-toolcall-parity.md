# ds2api Toolcall Parity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** 鍦?WebAI Gateway 浜у搧杈圭晫鍐呭鍒?ds2api 鏈€鏂板伐鍏疯皟鐢ㄩ€傞厤琛屼负锛岃 OpenAI/Anthropic 涓嬫父鎷垮埌绋冲畾銆乻chema 鍚堣銆乼ool_choice 鍚堣鐨勫伐鍏疯皟鐢ㄣ€?
**Architecture:** 浠?`webai_gateway.tool_bridge` 涓哄敮涓€宸ュ叿璋冪敤瑙ｆ瀽銆佷慨澶嶃€佸綊涓€鍖栧叆鍙ｏ紝OpenAI 涓?Anthropic 杈撳嚭灞傚鐢ㄥ悓涓€濂?`ToolBridgeContext`銆備笉鎶?ds2api 鐨?Gemini銆佽处鍙锋睜銆佹枃浠朵笂浼犮€佸巻鍙插悗鍙扮瓑闈?Gateway 鑱岃矗鍔熻兘鎼繘鏉ャ€?
**Tech Stack:** Python/FastAPI/pytest锛涗笂娓稿弬鑰冧负 `E:\ProjectX\_reference\ds2api` commit `3d52040b3b0420c6602d08a0627cb1078ed320aa`銆?
---

### Task 1: Schema-Aware Tool Argument Normalization

**Files:**
- Modify: `webai_gateway/tool_bridge.py`
- Test: `tests/test_ds2api_parity.py`

- [x] **Step 1: Write failing tests**

Add tests proving that parsed tool input is normalized against OpenAI `function.parameters`, Anthropic `input_schema`, and camelCase `inputSchema` before `to_openai_tool_calls`.

- [x] **Step 2: Verify RED**

Run: `python -m pytest tests/test_ds2api_parity.py -q`
Expected: new schema normalization tests fail because Gateway currently returns numeric/string-object values unchanged.

- [x] **Step 3: Implement minimal normalization**

Add ds2api-equivalent helpers:
- build schema index from `ToolBridgeContext.tools`
- recursively coerce schema `type=string`, string-only enum/const, and string/null union
- recursively handle object `properties` and `additionalProperties`
- recursively handle array `items`
- preserve ambiguous unions and non-object schemas

- [x] **Step 4: Verify GREEN**

Run: `python -m pytest tests/test_ds2api_parity.py -q`
Expected: tests pass.

### Task 2: ds2api Tool Choice Policy

**Files:**
- Modify: `webai_gateway/tool_bridge.py`
- Modify: `webai_gateway/openai_api.py`
- Modify: `webai_gateway/anthropic_api.py`
- Test: `tests/test_ds2api_parity.py`

- [x] **Step 1: Write failing tests**

Add tests proving:
- `tool_choice: "none"` disables prompt bridge even with `activation_policy=always`
- forced function/tool choice only exposes the forced tool
- `allowed_tools` filters exposed tools
- `required`/forced policy can be detected when the final assistant response has no valid tool call

- [x] **Step 2: Verify RED**

Run: `python -m pytest tests/test_ds2api_parity.py -q`
Expected: forced/allowed filtering and `none` tests fail on current code.

- [x] **Step 3: Implement policy parsing and propagation**

Add a `ToolChoicePolicy` dataclass mirroring ds2api modes `auto|none|required|forced`, parse OpenAI and Anthropic converted tool_choice, filter `ToolBridgeContext.tools`, and store policy on context.

- [x] **Step 4: Implement enforcement**

When policy requires a tool and the parsed result has no valid tool call, return a protocol-level `tool_choice_violation` signal for OpenAI/Anthropic adapters instead of silently treating it as normal text.

- [x] **Step 5: Verify GREEN**

Run: `python -m pytest tests/test_ds2api_parity.py tests/test_gateway.py -q`
Expected: new parity tests pass without regressing existing Gateway behavior.

### Task 3: Stream and Hidden-Thinking Parity

**Files:**
- Modify: `webai_gateway/tool_bridge.py`
- Modify: `webai_gateway/openai_api.py`
- Test: `tests/test_ds2api_parity.py`

- [x] **Step 1: Write failing tests**

Add tests proving:
- tool protocol blocks do not leak into SSE text output
- final SSE tool call arguments are schema-normalized
- hidden/detection thinking can produce a tool call only when visible text is empty

- [x] **Step 2: Verify RED**

Run: `python -m pytest tests/test_ds2api_parity.py -q`
Expected: schema-normalized SSE and hidden-thinking extraction tests fail where behavior is absent.

- [x] **Step 3: Implement parity helpers**

Reuse full-output parsing for Gateway stream stability, but match ds2api final semantics: sanitize leaked protocol, normalize tool call arguments against schemas, and expose a shared helper for raw/visible/thinking tool-call detection.

- [x] **Step 4: Verify GREEN**

Run: `python -m pytest tests/test_ds2api_parity.py -q`
Expected: stream/hidden-thinking parity tests pass.

### Task 4: Verification and Runtime Acceptance

**Files:**
- No production edits expected.

- [x] **Step 1: Run reference ds2api tests**

Run: `go test ./internal/toolcall ./internal/toolstream ./internal/httpapi/openai ./internal/httpapi/claude`
Expected: reference remains green at the pinned commit.

- [x] **Step 2: Run Gateway tests**

Run: `python -m pytest -q`
Expected: all Gateway tests pass.

- [x] **Step 3: Run frontend build**

Run: `cd webui; pnpm build`
Expected: build exits 0.

- [x] **Step 4: Restart local Gateway**

Run the project stop/start scripts, then request `http://127.0.0.1:8610/health`.
Expected: `ok=true`, `runtime.sourceFresh=true`, `runtime.sourceStale=false`.

- [x] **Step 5: Provider smoke**

Send harmless OpenAI-compatible tool-call smoke requests to `qwen-web/qwen3.6-plus` and `deepseek-v4-pro` when credentials are available.
Expected: both return standard `tool_calls` with schema-valid JSON arguments, or the report states the precise provider/network blocker without exposing credentials.
