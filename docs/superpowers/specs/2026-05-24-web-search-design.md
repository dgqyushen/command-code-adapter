# Web Search 功能设计

## 目标

在 CC-Adapter 中为 Anthropic Messages API (`/v1/messages`) 添加 web search 能力。当 AI 模型需要搜索时，适配器拦截 tool-call，调用外部搜索后端获取结果，注入回对话上下文。

## 架构概览

```
Claude Code                Adapter                          CC API                 DeepSeek
    |                        |                                |                       |
    |-- POST /v1/messages -->|                                |                       |
    |   (tools: [原有工具])   |                                |                       |
    |                        |-- 注入 web_search 工具定义 --->|                       |
    |                        |   POST /alpha/generate         |                       |
    |                        |   (tools: [原有 + web_search])  |                       |
    |                        |                                |                       |
    |                        |<-- SSE stream -----------------|                       |
    |                        |   event: tool-call             |                       |
    |                        |   toolName: "web_search"       |                       |
    |                        |                                |                       |
    |                        |  [拦截！不返回给 Claude Code]    |                       |
    |                        |                                |                       |
    |                        |-- 调用搜索 API ---------------->|                       |
    |                        |<-- 返回搜索结果 ----------------|                       |
    |                        |                                |                       |
    |                        |-- POST /alpha/generate ------->|                       |
    |                        |   (追加 tool-result 消息)       |                       |
    |                        |                                |                       |
    |                        |<-- SSE stream -----------------|                       |
    |                        |   event: text-delta...          |                       |
    |                        |<-- SSE stream -----------------|                       |
    |   (最终回答)            |                                |                       |
```

## 配置

```env
# 搜索后端: deepseek | brave | tavily
CC_ADAPTER_WEB_SEARCH_PROVIDER=deepseek

# DeepSeek 官方 API Key
CC_ADAPTER_DEEPSEEK_API_KEY=sk-xxx

# Optional: Brave / Tavily
CC_ADAPTER_BRAVE_API_KEY=BSA-xxx
CC_ADAPTER_TAVILY_API_KEY=tvly-xxx
```

## 改动文件

| 文件 | 改动 |
|------|------|
| `core/config.py` | 新增 `web_search_provider`, `deepseek_api_key`, `brave_api_key`, `tavily_api_key` |
| `providers/shared/web_search.py` | **新建** — web_search 工具定义、搜索执行、结果格式化 |
| `providers/anthropic/request.py` | `_build_body()` 中注入 `web_search` 工具到 tools 列表 |
| `providers/anthropic/response.py` | SSE 流中拦截 `web_search` tool-call，执行搜索，发起第二轮 CC 调用 |
| `providers/anthropic/router.py` | 适配流式/非流式的工具拦截与第二轮调用 |

## 核心流程

### 1. Request 阶段 (`request.py`)

在 `_build_body()` 中，当 `CC_ADAPTER_WEB_SEARCH_PROVIDER` 已配置时，向 `params["tools"]` 追
加 `web_search` 工具定义：

```json
{
  "name": "web_search",
  "description": "Search the web for current information",
  "input_schema": {
    "type": "object",
    "properties": {
      "query": {"type": "string", "description": "The search query"}
    },
    "required": ["query"]
  }
}
```

### 2. Response 拦截阶段 (`response.py`)

在 `translate_anthropic_stream()` 和 `collect_and_translate_anthropic_nonstream()` 中，检测
SSE 事件：

- `event_type == "tool-call"` 且 `toolName == "web_search"` 时 **拦截**（不发 SSE 给客户端）
- 提取 `input.query`，调用搜索后端
- 将搜索结果构造为 tool-result 消息
- 发起**第二轮** CC API 调用（追加 tool-result 到 messages）

### 3. 搜索后端 (`web_search.py`)

统一搜索接口：

```python
async def execute_search(query: str, provider: str, config) -> list[dict]:
    """返回搜索结果列表，每条包含 title, url, snippet"""
```

Provider 实现：

- **deepseek**: 调用 DeepSeek 官方 API 的搜索端点
- **brave**: 调用 Brave Search API
- **tavily**: 调用 Tavily Search API

### 4. Router 阶段 (`router.py`)

流式场景下，第二轮 CC 调用的 SSE 流直接返回给客户端（已翻译为 Anthropic 格式）。
非流式场景下，收集第二轮调用结果，构造 `AnthropicResponse` 返回。

## 错误处理

- 搜索 API 调用失败：构造错误 tool-result，让模型基于错误信息回复
- 第二轮 CC 调用失败：返回上游错误
- 搜索后端未配置：不注入 web_search 工具，保持原有行为

## 约束

- 仅在 Anthropic Messages API (`/v1/messages`) 路径实现
- 非流式 (`stream=False`) 和流式 (`stream=True`) 均需支持
- 搜索结果限制 10 条，单条 snippet 限制 500 字符，避免上下文爆炸
- 如果请求中已有同名 `web_search` 工具（来自 MCP），不覆盖
