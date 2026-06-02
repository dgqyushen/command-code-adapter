# Command Code Adapter

**中文** | [English](#english)

---

## 中文

将 [Command Code API](https://api.commandcode.ai) 暴露为兼容 OpenAI Chat Completions、Anthropic Messages 和 OpenAI Responses 格式的适配器。

支持**流式（SSE）**和**非流式**响应，附带 Web 管理面板。

### 快速开始

```bash
# 安装依赖
poetry install

# 配置 API Key
export CC_ADAPTER_CC_API_KEY=user_your_key_here

# 启动服务
poetry run python -m cc_adapter
```

服务启动后访问 `http://localhost:8080`，管理面板在 `http://localhost:8080/admin`。

### Docker

```bash
# 构建并运行
docker build -t cc-adapter .
docker run -p 8080:8080 -e CC_ADAPTER_CC_API_KEY=user_your_key_here cc-adapter

# 或使用 docker-compose（推荐）
# 编辑 .env 文件配置 CC_ADAPTER_CC_API_KEY，然后：
docker compose up -d
```

### 配置

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `CC_ADAPTER_CC_API_KEY` | — | Command Code API Key（必填） |
| `CC_ADAPTER_CC_BASE_URL` | `https://api.commandcode.ai` | CC API 地址 |
| `CC_ADAPTER_HOST` | `0.0.0.0` | 监听地址 |
| `CC_ADAPTER_PORT` | `8080` | 监听端口 |
| `CC_ADAPTER_LOG_LEVEL` | `INFO` | 日志级别 |
| `CC_ADAPTER_LOG_FORMAT` | `console` | 日志格式：`console` 或 `json` |
| `CC_ADAPTER_ADMIN_PASSWORD` | — | 管理面板密码（留空则无需认证） |
| `CC_ADAPTER_ACCESS_KEY` | — | API 访问密钥（留空则无需认证） |
| `CC_ADAPTER_DEFAULT_MODEL` | `deepseek/deepseek-v4-flash` | 管理面板 Playground 默认模型 |
| `CC_ADAPTER_HTTP_MAX_CONNECTIONS` | `200` | HTTP 连接池最大连接数 |
| `CC_ADAPTER_HTTP_MAX_KEEPALIVE_CONNECTIONS` | `50` | HTTP 连接池最大 Keepalive 连接数 |
| `CC_ADAPTER_HTTP2` | `false` | 启用 HTTP/2 |
| `CC_ADAPTER_ZDR` | `true` | 发送 `x-cmd-zdr: 1` 请求头（零数据留存） |
| `CC_ADAPTER_OSS_PRIMARY_PROVIDER` | — | 可选的 OSS 提供商名称，作为 `x-oss-primary-provider` 请求头发送 |
| `CC_ADAPTER_WEB_SEARCH_PROVIDER` | — | 设为 `deepseek` 时，将 Anthropic `web_search` 请求转发到 DeepSeek |
| `CC_ADAPTER_DEEPSEEK_API_KEY` | — | DeepSeek API Key，用于 `web_search` 转发 |
| `CC_ADAPTER_DEEPSEEK_ANTHROPIC_URL` | `https://api.deepseek.com/anthropic` | DeepSeek Anthropic 兼容端点 |
| `CC_ADAPTER_WEB_SEARCH_MODEL` | — | `web_search` 转发使用的 DeepSeek 模型；留空则使用请求中的模型 |

也可通过 `.env` 文件配置（参考 `.env.example`）。

### 日志

日志格式通过 `CC_ADAPTER_LOG_FORMAT` 控制（默认 `console`）。

**Console 格式**（默认）— 人眼可读的结构化单行日志：

```
07:42:18 INFO  app.start        base=https://api.commandcode.ai port=8080
07:42:31 INFO  openai.request   model=deepseek-v4-flash stream=true message_count=3 tools=true req=8f3a91c2
07:42:33 WARNING  upstream.retry   reason=empty_response attempt=1 max_attempts=2 req=8f3a91c2
07:42:34 INFO  upstream.usage   model=deepseek-v4-flash input=120 output=834 total=954 elapsed=2.1s req=8f3a91c2
07:42:34 INFO  http.done        method=POST path=/v1/chat/completions status_code=200 elapsed=2.48s req=8f3a91c2
```

**JSON 格式** — 机器解析用结构化格式：

```json
{"event": "http.done", "level": "info", "logger": "cc_adapter.main", "method": "POST", "path": "/v1/chat/completions", "status_code": 200, "elapsed": "2.480s", "request_id": "8f3a91c2", "timestamp": "2026-05-13T07:42:34Z"}
```

**事件列表：** `app.start`、`http.done`、`openai.request`、`anthropic.request`、`upstream.error`、`upstream.retry`、`upstream.usage`、`tool.call`、`auth.failed`、`admin.login.failed`、`admin.config.updated`、`admin.verify_key`

**脱敏：** 敏感字段（authorization、API key、messages、tool 编辑参数等）自动替换为 `***`。

### 使用

**OpenAI Chat Completions：**

```bash
curl http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-sonnet-4-6",
    "messages": [{"role": "user", "content": "Hello"}],
    "stream": true
  }'
```

**Anthropic Messages：**

```bash
curl http://localhost:8080/v1/messages \
  -H "Content-Type: application/json" \
  -H "x-api-key: sk-your-key" \
  -d '{
    "model": "claude-sonnet-4-6",
    "max_tokens": 1024,
    "messages": [{"role": "user", "content": "Hello"}]
  }'
```

兼容任意 OpenAI SDK：

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8080/v1",
    api_key="not-needed",
)
```

### Reasoning Effort

适配器支持 `reasoning_effort` 参数，用于控制模型的思考推理强度。

| 值 | 说明 |
|---|---|
| `"off"` | 关闭推理输出（响应端过滤 `reasoning-delta`） |
| `"low"` | 最小推理 |
| `"medium"` | 中等推理 |
| `"high"` | 较高推理 |
| `"xhigh"` | 高推理 |
| `"max"` | 最大推理 |
| `null` / 不传 | 不设推理 |

支持的取值因模型而异。适配器内置了 `MODEL_REASONING_EFFORTS_MAP`（来源：CC v0.26.7 客户端数据），当传入的强度值超出模型支持范围时，自动向上最近值（nearest-higher）映射。模型不在映射表中时不设该参数。

| 模型 | 支持的值 |
|---|---|
| deepseek/deepseek-v4-* | high, max |
| claude-sonnet-4-6, claude-opus-4-6/7 | low, medium, high, xhigh, max |
| gpt-5.5, gpt-5.4, gpt-5.3-codex | low, medium, high, xhigh |
| gpt-5.4-mini, claude-haiku-4-5 | low, medium, high |
| Qwen/Qwen3.6-Max-Preview, Qwen/Qwen3.6-Plus | low, medium, high |
| stepfun/Step-3.5-Flash | low, medium, high |

实现：对 `reasoning_effort` 按模型支持范围进行 clamp（nearest-higher）后透传给 CC API，不注入任何 system prompt。响应端保留 `reasoning-delta` 的过滤逻辑（`"off"` 模式下剥离 `reasoning_content`）。

```bash
curl http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "deepseek-v4-flash",
    "messages": [{"role": "user", "content": "Solve 2x+5=13"}],
    "reasoning_effort": "high",
    "stream": true
  }'
```

### 运行测试

```bash
poetry run pytest
```

### 目录结构

```
cc_adapter/
├── main.py                # FastAPI 应用入口与路由
├── core/                  # 基础设施
│   ├── config.py          #   配置管理（pydantic-settings）
│   ├── errors.py          #   错误处理与状态码映射
│   ├── logging.py         #   日志配置与中间件
│   ├── auth.py            #   认证逻辑（HMAC token）
│   ├── runtime.py         #   运行时单例（config/client/translator）
│   └── utils.py           #   工具函数
├── command_code/          # CC API 客户端
│   ├── client.py          #   HTTP 客户端
│   ├── headers.py         #   请求头构造
│   └── body.py            #   请求体构造
├── providers/             # 协议翻译
│   ├── openai/            #   OpenAI 兼容
│   │   ├── router.py      #   POST /v1/chat/completions
│   │   ├── models.py      #   数据模型
│   │   ├── request.py     #   OpenAI → CC
│   │   └── response.py    #   CC → OpenAI
│   ├── anthropic/         #   Anthropic 兼容
│   │   ├── router.py      #   POST /v1/messages
│   │   ├── models.py      #   数据模型
│   │   ├── request.py     #   Anthropic → CC
│   │   └── response.py    #   CC → Anthropic
│   └── shared/            #   共享工具
│       ├── model_mapping.py  # 模型名映射
│       └── tool_mapping.py   # 工具参数名映射
├── catalog/               # 数据目录
│   └── models_data.py     #   模型列表
└── admin/                 # Web 管理面板
    └── ...                #   管理界面
```

---

## English

### Quick Start

```bash
# Install dependencies
poetry install

# Configure API Key
export CC_ADAPTER_CC_API_KEY=user_your_key_here

# Start server
poetry run python -m cc_adapter
```

Once started, visit `http://localhost:8080`. The admin panel is at `http://localhost:8080/admin`.

### Docker

```bash
# Build and run
docker build -t cc-adapter .
docker run -p 8080:8080 -e CC_ADAPTER_CC_API_KEY=user_your_key_here cc-adapter

# Or use docker-compose (recommended)
# Edit the .env file to set CC_ADAPTER_CC_API_KEY, then:
docker compose up -d
```

### Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `CC_ADAPTER_CC_API_KEY` | — | Command Code API Key (required) |
| `CC_ADAPTER_CC_BASE_URL` | `https://api.commandcode.ai` | CC API base URL |
| `CC_ADAPTER_HOST` | `0.0.0.0` | Listen address |
| `CC_ADAPTER_PORT` | `8080` | Listen port |
| `CC_ADAPTER_LOG_LEVEL` | `INFO` | Log level |
| `CC_ADAPTER_LOG_FORMAT` | `console` | Log format: `console` or `json` |
| `CC_ADAPTER_ADMIN_PASSWORD` | — | Admin panel password (leave blank for no auth) |
| `CC_ADAPTER_ACCESS_KEY` | — | API access key (leave blank for no auth) |
| `CC_ADAPTER_DEFAULT_MODEL` | `deepseek/deepseek-v4-flash` | Admin Playground default model |
| `CC_ADAPTER_HTTP_MAX_CONNECTIONS` | `200` | HTTP connection pool max connections |
| `CC_ADAPTER_HTTP_MAX_KEEPALIVE_CONNECTIONS` | `50` | HTTP connection pool max keepalive connections |
| `CC_ADAPTER_HTTP2` | `false` | Enable HTTP/2 |
| `CC_ADAPTER_ZDR` | `true` | Send `x-cmd-zdr: 1` header (zero data retention) |
| `CC_ADAPTER_OSS_PRIMARY_PROVIDER` | — | Optional OSS provider name, sent as `x-oss-primary-provider` header |
| `CC_ADAPTER_WEB_SEARCH_PROVIDER` | — | Set to `deepseek` to forward Anthropic `web_search` requests to DeepSeek |
| `CC_ADAPTER_DEEPSEEK_API_KEY` | — | DeepSeek API key used for `web_search` forwarding |
| `CC_ADAPTER_DEEPSEEK_ANTHROPIC_URL` | `https://api.deepseek.com/anthropic` | DeepSeek Anthropic-compatible endpoint |
| `CC_ADAPTER_WEB_SEARCH_MODEL` | — | DeepSeek model used for `web_search` forwarding; empty means use the request model |

You can also configure via a `.env` file (see `.env.example`).

### Logging

The log format is controlled by `CC_ADAPTER_LOG_FORMAT` (default: `console`).

**Console format** (default) — human-readable single-line logs:

```
07:42:18 INFO  app.start        base=https://api.commandcode.ai port=8080
07:42:31 INFO  openai.request   model=deepseek-v4-flash stream=true message_count=3 tools=true req=8f3a91c2
07:42:33 WARNING  upstream.retry   reason=empty_response attempt=1 max_attempts=2 req=8f3a91c2
07:42:34 INFO  upstream.usage   model=deepseek-v4-flash input=120 output=834 total=954 elapsed=2.1s req=8f3a91c2
07:42:34 INFO  http.done        method=POST path=/v1/chat/completions status_code=200 elapsed=2.48s req=8f3a91c2
```

**JSON format** — structured for machine parsing:

```json
{"event": "http.done", "level": "info", "logger": "cc_adapter.main", "method": "POST", "path": "/v1/chat/completions", "status_code": 200, "elapsed": "2.480s", "request_id": "8f3a91c2", "timestamp": "2026-05-13T07:42:34Z"}
```

**Event names:** `app.start`, `http.done`, `openai.request`, `anthropic.request`, `upstream.error`, `upstream.retry`, `upstream.usage`, `tool.call`, `auth.failed`, `admin.login.failed`, `admin.config.updated`, `admin.verify_key`

**Redaction:** Sensitive fields (authorization, API keys, messages, tool edit parameters) are automatically replaced with `***`.

### Usage

**OpenAI Chat Completions:**

```bash
curl http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-sonnet-4-6",
    "messages": [{"role": "user", "content": "Hello"}],
    "stream": true
  }'
```

**Anthropic Messages:**

```bash
curl http://localhost:8080/v1/messages \
  -H "Content-Type: application/json" \
  -H "x-api-key: sk-your-key" \
  -d '{
    "model": "claude-sonnet-4-6",
    "max_tokens": 1024,
    "messages": [{"role": "user", "content": "Hello"}]
  }'
```

Compatible with any OpenAI SDK:

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8080/v1",
    api_key="not-needed",
)
```

### Reasoning Effort

The adapter supports the `reasoning_effort` parameter to control the model's reasoning/thinking intensity.

| Value | Description |
|---|---|
| `"off"` | Suppress reasoning output (response-side `reasoning-delta` filtering) |
| `"low"` | Minimal reasoning |
| `"medium"` | Moderate reasoning |
| `"high"` | High reasoning |
| `"xhigh"` | Extra high reasoning |
| `"max"` | Maximum reasoning |
| `null` / not set | No reasoning effort set |

Supported values vary per model. The adapter uses `MODEL_REASONING_EFFORTS_MAP` (sourced from CC v0.26.7 client data). When a value exceeds a model's supported range, it is clamped to the nearest higher supported value. Models not in the map get no `reasoning_effort` param.

| Model | Supported Values |
|---|---|
| deepseek/deepseek-v4-* | high, max |
| claude-sonnet-4-6, claude-opus-4-6/7 | low, medium, high, xhigh, max |
| gpt-5.5, gpt-5.4, gpt-5.3-codex | low, medium, high, xhigh |
| gpt-5.4-mini, claude-haiku-4-5 | low, medium, high |
| Qwen/Qwen3.6-Max-Preview, Qwen/Qwen3.6-Plus | low, medium, high |
| stepfun/Step-3.5-Flash | low, medium, high |

Implementation: clamps `reasoning_effort` to the model's supported range (nearest-higher), then forwards to CC API. **No system prompt injection**. Response-side filtering strips `reasoning-delta` events when set to `"off"`.

```bash
curl http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "deepseek-v4-flash",
    "messages": [{"role": "user", "content": "Solve 2x+5=13"}],
    "reasoning_effort": "high",
    "stream": true
  }'
```

### Running Tests

```bash
poetry run pytest
```

### Directory Structure

```
cc_adapter/
├── main.py                # FastAPI app entry & routes
├── core/                  # Infrastructure
│   ├── config.py          #   Configuration (pydantic-settings)
│   ├── errors.py          #   Error handling & status code mapping
│   ├── logging.py         #   Logging & middleware
│   ├── auth.py            #   Auth (HMAC token)
│   ├── runtime.py         #   Runtime singletons
│   └── utils.py           #   Utility functions
├── command_code/          # CC API client
│   ├── client.py          #   HTTP client
│   ├── headers.py         #   Request headers
│   └── body.py            #   Request body builder
├── providers/             # Protocol translators
│   ├── openai/            #   OpenAI-compatible
│   │   ├── router.py      #   POST /v1/chat/completions
│   │   ├── models.py      #   Data models
│   │   ├── request.py     #   OpenAI → CC
│   │   └── response.py    #   CC → OpenAI
│   ├── anthropic/         #   Anthropic-compatible
│   │   ├── router.py      #   POST /v1/messages
│   │   ├── models.py      #   Data models
│   │   ├── request.py     #   Anthropic → CC
│   │   └── response.py    #   CC → Anthropic
│   └── shared/            #   Shared utilities
│       ├── model_mapping.py  # Model name mapping
│       └── tool_mapping.py   # Tool param name mapping
├── catalog/               # Data directory
│   └── models_data.py     #   Model listings
└── admin/                 # Web admin panel
    └── ...                #   Admin interface
```

### License

MIT
