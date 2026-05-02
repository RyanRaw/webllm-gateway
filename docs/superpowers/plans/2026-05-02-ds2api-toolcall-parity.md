# ds2api 工具调用 100% 复刻与验证计划

## 基线

- ds2api 本地参考仓库：`E:\ProjectX\_reference\ds2api`
- 发布基线：`origin/main`，提交 `3d52040b3b0420c6602d08a0627cb1078ed320aa`
- 最新开发分支：`origin/dev`，提交 `e620752`
- 已核对：`origin/main..origin/dev` 在以下工具调用相关路径没有 diff，因此本次复刻以 `origin/main` 当前发布代码为基线：
  - `internal/toolcall`
  - `internal/toolstream`
  - `internal/js/helpers/stream-tool-sieve`
  - `internal/httpapi/openai/shared`
  - `internal/httpapi/openai/chat`
  - `internal/httpapi/openai/responses`
  - `tests/node`

## 复刻边界

本项目不复制 ds2api 的账号、服务端、前端和下游工具执行能力。WebAI Gateway 的边界仍然是协议适配层，不执行本地工具。

本次“100% 复刻”定义为：对网页模型输出到标准 OpenAI/Anthropic tool call 的关键链路，逐项复刻 ds2api 最新行为：

- DSML/XML 工具调用 wrapper 识别。
- DSML 标签噪声归一化。
- CDATA、嵌套 XML、数组和 JSON scalar 参数解析。
- fenced code 中示例工具调用不被执行。
- 缺失 opening wrapper 的有限修复。
- malformed wrapper、legacy body、空参数等拒绝策略。
- OpenAI `tool_calls` id、arguments 格式。
- 流式输出中工具协议不泄漏给下游。
- leaked output 清理：空 JSON fence、wire tool call/result、DeepSeek 特殊 token、`think`、agent XML wrapper。

Gateway 保留两个受控超集能力，不计入 ds2api parity 缺口：

- 历史兼容的 fenced `tool_json`。
- 针对 Qwen 网页实测输出的 embedded JSON tool call 修复。

这两个能力只作为 Gateway 额外兼容层存在，DSML/XML parity 测试不会依赖它们。

## 执行清单

- [x] 同步 ds2api 参考仓库并确认最新提交。
- [x] 比对 `origin/main..origin/dev` 的工具调用相关路径。
- [x] 新增 Gateway 独立 parity 测试文件，直接覆盖 ds2api Go/Node 关键用例。
- [x] 先运行 parity 测试，确认真实缺口。
- [x] 修复解析器差异，不做无关重构。
- [x] 运行 ds2api 上游相关测试，证明参考基线自身通过。
- [x] 运行 Gateway 针对性 parity 测试。
- [x] 运行 Gateway 完整后端测试。
- [x] 重启本机 Gateway 并验证 `/health`。
- [x] 做一个无敏感内容的真实网页登录模型 tool-call smoke。

## 验收命令

```powershell
git -C E:\ProjectX\_reference\ds2api diff --name-status origin/main..origin/dev -- internal/toolcall internal/toolstream internal/js/helpers/stream-tool-sieve internal/httpapi/openai/shared internal/httpapi/openai/chat internal/httpapi/openai/responses tests/node
go test ./internal/toolcall ./internal/httpapi/openai ./internal/httpapi/openai/shared
node --test tests/node/stream-tool-sieve.test.js
python -m pytest -q tests\test_ds2api_parity.py
python -m pytest -q tests\test_gateway.py -k "ds2api or toolu_alias or cmd_cd_drive_switch or clarification_final"
python -m pytest -q
python -m compileall -q webai_gateway
```

## 验收结果

- ds2api 参考仓库：`go test ./internal/toolcall ./internal/httpapi/openai ./internal/httpapi/openai/shared` 通过。
- ds2api 参考仓库：`node --test tests\node\stream-tool-sieve.test.js` 通过，57 个 Node sieve 用例全部通过。
- Gateway parity：`python -m pytest -q tests\test_ds2api_parity.py` 通过，13 个迁移用例全部通过。
- Gateway 旧回归：`python -m pytest -q tests\test_gateway.py -k "ds2api or toolu_alias or cmd_cd_drive_switch or clarification_final or embedded_json_tool_call"` 通过，28 个相关用例全部通过。
- Gateway 全量后端：`python -m pytest -q` 通过，535 个用例全部通过。
- Gateway 编译：`python -m compileall -q webai_gateway` 通过。
- Gateway 服务已重启：PID `3584`，`/health` 返回 `ok=true`、`runtime.sourceFresh=true`、`runtime.sourceStale=false`。
- `/v1/models` 仍展示 `deepseek-v4-pro`。
- 真实 Qwen Web smoke：`qwen-web/qwen3.6-plus` 对 `Read README.md` 返回标准 OpenAI `tool_calls`，`finish_reason=tool_calls`，工具名 `Read`，参数 `{"file_path":"README.md"}`，id 前缀 `call_`。
- 真实 DeepSeek V4 Pro smoke：`deepseek-v4-pro` 对 `Read README.md` 返回标准 OpenAI `tool_calls`，`finish_reason=tool_calls`，工具名 `Read`，参数 `{"file_path":"README.md"}`，id 前缀 `call_`。
