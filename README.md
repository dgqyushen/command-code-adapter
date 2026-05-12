# Command Code Adapter

**中文** | [English](#english)

---

## 中文

OpenAI Chat Completions 兼容适配器，将 [Command Code API](https://api.commandcode.ai) 暴露为标准 OpenAI 格式。

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
| `CC_ADAPTER_ADMIN_PASSWORD` | — | 管理面板密码（留空则无需认证） |
| `CC_ADAPTER_ACCESS_KEY` | — | `/v1/chat/completions` 访问密钥（留空则无需认证） |
| `CC_ADAPTER_DEFAULT_MODEL` | `deepseek/deepseek-v4-flash` | 管理面板 Playground 默认模型 |

也可通过 `.env` 文件配置（参考 `.env.example`）。

### 使用

```bash
curl http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-sonnet-4-6",
    "messages": [{"role": "user", "content": "Hello"}],
    "stream": true
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
| `"off"` | 关闭推理输出（system prompt 抑制 + 响应端过滤 `reasoning-delta`） |
| `"low"` | 最小推理 |
| `"medium"` | 默认推理强度（不注入 system prompt） |
| `"high"` | 逐步推理思考 |
| `"xhigh"` | 详细推理思考 |
| `"max"` | 最大推理强度 |
| `null` / 不传 | 原行为，不做任何处理 |

底层实现采用**双通道策略**：
1. **CC API 透传**：将 `reasoning_effort` 原样传递给 CC API，未来 CC 原生支持后自动生效
2. **System Prompt 注入**：根据强度级别向请求追加推理指令（`"medium"` 除外）
3. **响应端过滤**：`"off"` 模式下过滤 CC 返回的 `reasoning-delta` 事件，剥离 `reasoning_content`

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
| `CC_ADAPTER_ADMIN_PASSWORD` | — | Admin panel password (leave blank for no auth) |
| `CC_ADAPTER_ACCESS_KEY` | — | `/v1/chat/completions` access key (leave blank for no auth) |
| `CC_ADAPTER_DEFAULT_MODEL` | `deepseek/deepseek-v4-flash` | Admin Playground default model |

You can also configure via a `.env` file (see `.env.example`).

### Usage

```bash
curl http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-sonnet-4-6",
    "messages": [{"role": "user", "content": "Hello"}],
    "stream": true
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
| `"off"` | Suppress reasoning output (system prompt + response-side `reasoning-delta` filtering) |
| `"low"` | Minimal reasoning |
| `"medium"` | Default reasoning (no system prompt injection) |
| `"high"` | Step-by-step reasoning |
| `"xhigh"` | Detailed reasoning |
| `"max"` | Maximum reasoning |
| `null` / not set | Current behavior, no intervention |

The implementation uses a **dual-path strategy**:
1. **CC API passthrough**: forwards `reasoning_effort` to CC API for future native support
2. **System prompt injection**: appends reasoning instructions based on the level (except `"medium"`)
3. **Response filtering**: strips `reasoning-delta` events and `reasoning_content` when set to `"off"`

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
