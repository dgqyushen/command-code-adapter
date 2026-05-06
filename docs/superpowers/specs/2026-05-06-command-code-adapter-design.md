# Command Code OpenAI Adapter — 设计文档

> 将 Command Code API 通过 OpenAI Chat Completions 格式暴露给第三方客户端
> 日期：2026-05-06

---

## 1. 概述

构建一个 HTTP 反向代理适配器，接收 **OpenAI Chat Completions 格式** 的请求（`POST /v1/chat/completions`），内部转换为 **Command Code API**（`POST /alpha/generate`）的请求格式，并将响应实时转换回 OpenAI 格式返回给客户端。

### 目标

- 让任何支持 OpenAI API 的客户端工具（如 Cursor、Continue.dev、OpenAI SDK、curl 等）能够调用 Command Code 的模型能力
- 支持流式（SSE）和非流式两种响应模式
- 不支持/不存在的参数以日志形式输出警告，不报错中断

---

## 2. 技术选型

| 层 | 选择 |
|----|------|
| 语言 | Python 3.11+ |
| 包管理 | Poetry |
| HTTP 框架 | FastAPI |
| HTTP 客户端 | httpx（异步） |
| 配置 | pydantic-settings + .env |
| 测试 | pytest + httpx mock |

---

## 3. 项目结构

```
~/codes/command-code-adapter/
├── pyproject.toml
├── .env.example
├── README.md
├── cc_adapter/
│   ├── __init__.py
│   ├── main.py                 # FastAPI 应用入口 + 路由
│   ├── config.py               # pydantic-settings 配置加载
│   ├── models/
│   │   ├── __init__.py
│   │   ├── openai.py           # OpenAI ChatCompletions 请求/响应 Pydantic 模型
│   │   └── command_code.py     # Command Code 事件/响应 Pydantic 模型
│   ├── translator/
│   │   ├── __init__.py
│   │   ├── request.py          # OpenAI → Command Code 请求转换
│   │   └── response.py         # Command Code → OpenAI 响应转换
│   ├── client.py               # httpx 封装，向 Command Code API 发送请求
│   └── errors.py               # 异常定义 + HTTP 错误映射
└── tests/
    ├── __init__.py
    ├── test_request_translator.py
    ├── test_response_translator.py
    └── test_integration.py
```

---

## 4. API 路由

### `POST /v1/chat/completions`

唯一公开路由。接收 OpenAI Chat Completions 请求，返回 OpenAI Chat Completions 响应。

### `GET /health`

健康检查端点。

### `GET /v1/models`

返回可用的 Command Code 模型列表（可选）。

---

## 5. 请求转换（OpenAI → Command Code）

### 5.1 参数映射

| OpenAI 参数 | 映射目标 | 处理 |
|------------|---------|------|
| `model` | `params.model` | 直接透传 |
| `messages` | `params.messages` + `params.system` | system 消息提取到 `params.system`，其余放 `params.messages` |
| `tools` | `params.tools` | 直接透传（结构基本兼容） |
| `tool_choice` | — | 日志警告，忽略 |
| `max_tokens` | `params.max_tokens` | 直接透传，默认 64000 |
| `temperature` | `params.temperature` | 直接透传 |
| `top_p` | — | 日志警告，忽略 |
| `stop` | — | 日志警告，忽略 |
| `n` | — | 日志警告，忽略 |
| `presence_penalty` | — | 日志警告，忽略 |
| `frequency_penalty` | — | 日志警告，忽略 |
| `user` | — | 日志警告，忽略 |
| `stream` | `params.stream` | 直接透传 |
| `response_format` | — | 日志警告，忽略 |

### 5.2 构建的 Command Code Request Body

```json
{
  "config": { "env": "adapter" },
  "memory": "",
  "taste": null,
  "skills": null,
  "permissionMode": "standard",
  "params": {
    "model": "<from request>",
    "messages": ["<translated messages>"],
    "tools": ["<translated tools or null>"],
    "system": "<extracted system prompt or null>",
    "max_tokens": "<from request or 64000>",
    "stream": "<from request>"
  }
}
```

### 5.3 构建的 Command Code Headers

| Header | 值 |
|--------|-----|
| `Authorization` | `Bearer <CC_API_KEY>` |
| `Content-Type` | `application/json` |
| `x-cli-environment` | `production` |
| `x-project-slug` | `adapter` |
| `x-internal-team-flag` | `false` |
| `x-taste-learning` | `false` |
| `x-command-code-version` | `0.25.2-adapter` |

---

## 6. 响应转换（Command Code → OpenAI）

### 6.1 SSE 事件映射

| Command Code 事件 | → OpenAI SSE |
|------------------|-------------|
| `text-delta` | `choices[0].delta.content` |
| `reasoning-delta` | 忽略，日志记录 |
| `reasoning-end` | 忽略 |
| `tool-call` | `choices[0].delta.tool_calls[0]`（转为 OpenAI function 格式） |
| `tool-result` | 忽略（OpenAI 不返回 tool result） |
| `finish` | final chunk + `usage` + `data: [DONE]` |
| `error` | HTTP 500 或 SSE error |

### 6.2 finish_reason 映射

| Command Code | OpenAI |
|-------------|--------|
| `end_turn` | `stop` |
| `tool_calls` | `tool_calls` |

### 6.3 非流式模式

adapter 内部以 `stream: true` 请求 CC，收完所有 SSE 事件后组装为单个 `ChatCompletionResponse` JSON 返回。

### 6.4 流式模式

每收到一个 CC SSE 事件，即时构建 OpenAI SSE chunk，以 `data: <json>\n\n` 格式实时推送。结束时发送 `data: [DONE]\n\n`。

### 6.5 OpenAI 响应 ID 格式

使用 `chatcmpl-<uuid>` 格式生成响应 ID。

---

## 7. 错误处理

### 错误映射

| Command Code API 错误 | OpenAI 格式 |
|----------------------|-------------|
| 401 Unauthorized | `{"error":{"message":"Authentication failed","type":"authentication_error","code":401}}` |
| 429 Too Many Requests | `{"error":{"message":"Rate limit exceeded","type":"rate_limit_error","code":429}}` |
| 400 Bad Request | `{"error":{"message":"...","type":"invalid_request_error","code":400}}` |
| 5xx Server Error | `{"error":{"message":"Upstream server error","type":"api_error","code":502}}` |
| 网络超时 | `{"error":{"message":"Request timed out","type":"timeout_error","code":504}}` |

### 日志

所有未支持的参数以 `WARNING` 级别日志记录。CC API 错误、网络错误等以 `ERROR` 级别记录。

---

## 8. 配置

通过 pydantic-settings 从环境变量或 `.env` 文件加载：

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `CC_API_KEY` | — | （必填）Command Code API Key |
| `CC_BASE_URL` | `https://api.commandcode.ai` | Command Code API 地址 |
| `CC_ADAPTER_HOST` | `0.0.0.0` | 监听地址 |
| `CC_ADAPTER_PORT` | `8080` | 监听端口 |
| `CC_ADAPTER_LOG_LEVEL` | `INFO` | 日志级别 |

---

## 9. 测试策略

### 单元测试
- `test_request_translator.py`：验证 OpenAI → CC 请求转换的每个映射规则
- `test_response_translator.py`：验证 CC 事件 → OpenAI 响应的组装逻辑

### 集成测试
- `test_integration.py`：FastAPI TestClient + mock httpx，验完整 request → response 链路

### 手动验证
```bash
# 非流式
curl http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"claude-sonnet-4-6","messages":[{"role":"user","content":"hello"}],"stream":false}'

# 流式
curl http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"claude-sonnet-4-6","messages":[{"role":"user","content":"hello"}],"stream":true}'
```

---

## 10. 限制与注意事项

1. Command Code 的 `config`、`memory`、`taste`、`skills`、`permissionMode` 等专有字段在 adapter 中用固定默认值填充
2. 不支持 `response_format`（JSON mode），即使 CC 后端支持
3. 不支持 `vision` 图像输入（CC API 支持但 OpenAI messages 格式需额外转换）
4. 不支持 `tool_choice` 控制
5. 不支持 `stop` 序列
6. 不同模型的 context window、token 限制以 CC 后端为准
