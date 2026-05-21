# Media Generation

Gateway 提供 OpenAI-compatible 的图片包装接口。媒体生成依赖 WebAI2API sidecar 的网页登录能力；Gateway 只负责协议包装、鉴权和错误透传。

## Image generation

Endpoint:

```text
POST /v1/images/generations
```

推荐模型：

```text
gpt-image-2
```

兼容模型：

```text
gpt-image-1.5
chatgpt/gpt-image-2
chatgpt/gpt-image-1.5
```

限制：

- 当前只支持 `n=1`。
- `response_format` 支持 `url` 和 `b64_json`。
- `url` 返回的是 data URI，不是公网文件地址。
- 需要对应 WebAI2API adapter 的网页登录态可用，例如 ChatGPT。
- 首页授权入口会在缺少对应 worker 时自动创建隔离 WebAI2API profile/worker；用户只需要完成网页登录授权，然后点击“恢复 API 并刷新”。
- 图生图 / 参考图可传 `input_image`、`image`、`reference_image` 或 `input_reference`，值可以是单个 `data:image/...`，也可以是数组；Gateway 会把它们转成 WebAI2API 所需的 OpenAI 多模态 `image_url` 消息。
- 未通过真实链路验证的媒体/视频模型当前先从用户入口、模型目录和媒体 API 关闭，避免用户误用。

PowerShell 示例：

```powershell
$key = (Get-Content -Raw config.json | ConvertFrom-Json).server.apiKey
$body = @{
  model = "gpt-image-2"
  prompt = "一只蓝色玻璃质感的未来感小机器人，产品摄影风格"
  n = 1
  response_format = "b64_json"
} | ConvertTo-Json

$result = Invoke-RestMethod `
  -Uri "http://127.0.0.1:8610/v1/images/generations" `
  -Method Post `
  -Headers @{ Authorization = "Bearer $key" } `
  -ContentType "application/json" `
  -Body $body

[IO.File]::WriteAllBytes("output.png", [Convert]::FromBase64String($result.data[0].b64_json))
```

## Frontend smoke test

首页“图片生成测试”区域可以直接调用 `/v1/images/generations`。它用于验证网页登录态和 Gateway 包装是否可用，不替代完整的图片工作台。
