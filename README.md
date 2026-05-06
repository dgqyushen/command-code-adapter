# Command Code Adapter

OpenAI Chat Completions 兼容适配器，用于将 Command Code API 暴露为 OpenAI 格式。

## 快速开始

```bash
# 安装依赖
poetry install

# 配置 API Key
export CC_API_KEY=user_your_key_here

# 启动服务
poetry run python -m cc_adapter
```

## 配置

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `CC_API_KEY` | — | Command Code API Key（必填） |
| `CC_BASE_URL` | `https://api.commandcode.ai` | CC API 地址 |
| `CC_ADAPTER_HOST` | `0.0.0.0` | 监听地址 |
| `CC_ADAPTER_PORT` | `8080` | 监听端口 |
| `CC_ADAPTER_LOG_LEVEL` | `INFO` | 日志级别 |

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

支持任意 OpenAI SDK：

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8080/v1",
    api_key="not-needed",  # 实际使用 CC_API_KEY
)
```

## 项目结构

```
cc_adapter/
├── main.py          # FastAPI 应用
├── config.py        # 配置
├── models/          # Pydantic 数据模型
├── translator/      # 请求/响应格式转换
├── client.py        # CC API HTTP 客户端
└── errors.py        # 错误处理
```

## 限制

详见 `docs/superpowers/specs/2026-05-06-command-code-adapter-design.md`
