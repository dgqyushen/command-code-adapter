# Command Code Adapter

OpenAI Chat Completions 兼容适配器，将 [Command Code API](https://api.commandcode.ai) 暴露为标准 OpenAI 格式。

支持**流式（SSE）**和**非流式**响应，附带 Web 管理面板。

## 快速开始

```bash
# 安装依赖
poetry install

# 配置 API Key
export CC_API_KEY=user_your_key_here

# 启动服务
poetry run python -m cc_adapter
```

服务启动后访问 `http://localhost:8080`，管理面板在 `http://localhost:8080/admin`。

## Docker

```bash
# 构建并运行
docker build -t cc-adapter .
docker run -p 8080:8080 -e CC_API_KEY=user_your_key_here cc-adapter

# 或使用 docker-compose（推荐）
# 编辑 .env 文件配置 CC_API_KEY，然后：
docker compose up -d
```

## 配置

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `CC_API_KEY` | — | Command Code API Key（必填） |
| `CC_BASE_URL` | `https://api.commandcode.ai` | CC API 地址 |
| `CC_ADAPTER_HOST` | `0.0.0.0` | 监听地址 |
| `CC_ADAPTER_PORT` | `8080` | 监听端口 |
| `CC_ADAPTER_LOG_LEVEL` | `INFO` | 日志级别 |
| `CC_ADAPTER_ADMIN_PASSWORD` | — | 管理面板密码（留空则无需认证） |
| `CC_ADAPTER_ACCESS_KEY` | — | `/v1/chat/completions` 访问密钥（留空则无需认证） |
| `CC_ADAPTER_DEFAULT_MODEL` | `deepseek/deepseek-v4-flash` | 管理面板 Playground 默认模型 |

也可通过 `.env` 文件配置（参考 `.env.example`）。

## 使用

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

## 运行测试

```bash
poetry run pytest
```

## 目录结构

```
cc_adapter/
├── main.py                # FastAPI 应用入口与路由
├── config.py              # 配置管理（pydantic-settings）
├── models/                # Pydantic 数据模型
│   ├── openai.py          #   OpenAI ChatCompletions 格式
│   └── command_code.py    #   Command Code API 格式
├── translator/            # 请求/响应格式转换
│   ├── request.py         #   OpenAI → CC
│   ├── response.py        #   CC → OpenAI
│   └── tool_mapping.py    #   工具参数名双向映射
├── client.py              # CC API HTTP 客户端
├── errors.py              # 错误处理与状态码映射
└── admin/                 # Web 管理面板
    ├── router.py          #   REST API 端点
    ├── auth.py            #   认证逻辑
    └── static/            #   前端静态文件
        ├── index.html
        ├── admin.css
        └── admin.js
```

## 许可证

MIT
