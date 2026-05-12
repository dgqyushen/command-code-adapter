#!/usr/bin/env bash
# ===================================================
# CC-Adapter 端到端测试脚本
# 用法: CC_ADAPTER_KEY=<access_key> bash tests/e2e_test.sh
# 环境变量:
#   CC_ADAPTER_KEY  - access_key (来自 .env 的 CC_ADAPTER_ACCESS_KEY)
#   BASE_URL        - 适配器地址 (默认 http://localhost:8081)
# ===================================================
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8081}"
CC_KEY="${CC_ADAPTER_KEY:?必须设置 CC_ADAPTER_KEY}"

PASS=0
FAIL=0

check() {
    local name="$1" expected="$2" actual="$3"
    if [ "$actual" = "$expected" ]; then
        echo "  ✅ PASS: $name"
        ((PASS++))
    else
        echo "  ❌ FAIL: $name"
        echo "     expected: $expected"
        echo "     actual:   $actual"
        ((FAIL++))
    fi
}

check_contains() {
    local name="$1" substr="$2" output="$3"
    if echo "$output" | grep -Fq "$substr"; then
        echo "  ✅ PASS: $name"
        ((PASS++))
    else
        echo "  ❌ FAIL: $name"
        echo "     expected to contain: $substr"
        echo "     output: $(echo "$output" | head -3)"
        ((FAIL++))
    fi
}

echo ""
echo "=========================================="
echo " CC-Adapter 端到端测试"
echo " Base URL: $BASE_URL"
echo "=========================================="
echo ""

# ============== 1. /v1/models ==============
echo "--- 1. /v1/models ---"

MODELS_RESP=$(curl -s --max-time 10 "$BASE_URL/v1/models")
check_contains "返回 object=list" '"object":"list"' "$MODELS_RESP"
check_contains "包含 stepfun/Step-3.5-Flash" '"id":"stepfun/Step-3.5-Flash"' "$MODELS_RESP"
check_contains "包含 claude-sonnet-4-6" '"id":"claude-sonnet-4-6"' "$MODELS_RESP"
check_contains "包含 gpt-5.4" '"id":"gpt-5.4"' "$MODELS_RESP"

MODEL_COUNT=$(echo "$MODELS_RESP" | python3 -c "import sys,json; print(len(json.load(sys.stdin)['data']))")
check "共 19 个模型" "19" "$MODEL_COUNT"

echo ""

# ============== 2. /v1/chat/completions (OpenAI) ==============
echo "--- 2. /v1/chat/completions (OpenAI, streaming) ---"

OPENAI_RESP=$(curl -s --max-time 60 -N -X POST "$BASE_URL/v1/chat/completions" \
  -H "content-type: application/json" \
  -H "Authorization: Bearer $CC_KEY" \
  -d '{
    "model": "step-3-5-flash",
    "messages": [{"role": "user", "content": "Say hello in one word"}],
    "max_tokens": 50,
    "stream": true
  }' 2>/dev/null)

check_contains "返回 data: [DONE]" "[DONE]" "$OPENAI_RESP"
check_contains "包含 model=step-3-5-flash" 'step-3-5-flash' "$OPENAI_RESP"
FINAL_LINE=$(echo "$OPENAI_RESP" | grep -v "^data: " | tail -1)
echo ""

# ============== 3. /v1/messages (Anthropic) ==============
echo "--- 3. /v1/messages (Anthropic, streaming) ---"

ANTH_RESP=$(curl -s --max-time 60 -N -X POST "$BASE_URL/v1/messages" \
  -H "content-type: application/json" \
  -H "x-api-key: $CC_KEY" \
  -H "anthropic-version: 2023-06-01" \
  -d '{
    "model": "step-3-5-flash",
    "max_tokens": 50,
    "messages": [{"role": "user", "content": "Say hello in one word"}],
    "stream": true
  }' 2>/dev/null)

check_contains "返回 message_start" "message_start" "$ANTH_RESP"
check_contains "返回 message_stop" "message_stop" "$ANTH_RESP"
# model 在 message_start 的 data 里
ANTH_MODEL=$(echo "$ANTH_RESP" | grep "message_start" | python3 -c "import sys,json; print(json.loads(sys.stdin.read().split('data: ')[1])['message']['model'])" 2>/dev/null || echo "not_found")
check "anthropic model=step-3-5-flash" "step-3-5-flash" "$ANTH_MODEL"
echo ""

# ============== 4. OpenAI 模拟工具调用 ==============
echo "--- 4. OpenAI 工具调用 (non-streaming) ---"

TOOL_OPENAI_RESP=$(curl -s --max-time 120 -X POST "$BASE_URL/v1/chat/completions" \
  -H "content-type: application/json" \
  -H "Authorization: Bearer $CC_KEY" \
  -d '{
    "model": "step-3-5-flash",
    "messages": [{"role": "user", "content": "Read /tmp/test.txt"}],
    "max_tokens": 200,
    "stream": false,
    "tools": [
      {
        "type": "function",
        "function": {
          "name": "Read",
          "description": "Read a file",
          "parameters": {
            "type": "object",
            "properties": {
              "filePath": {"type": "string", "description": "path to file"}
            },
            "required": ["filePath"]
          }
        }
      }
    ],
    "tool_choice": "auto"
  }' 2>/dev/null)

check_contains "返回 finish_reason" "finish_reason" "$TOOL_OPENAI_RESP"
check_contains "返回 tool_calls" "tool_calls" "$TOOL_OPENAI_RESP" || \
  check_contains "返回 content (文本回复)" "content" "$TOOL_OPENAI_RESP"
echo ""

# ============== 5. Anthropic 模拟工具调用 ==============
echo "--- 5. Anthropic 工具调用 (non-streaming) ---"

TOOL_ANTH_RESP=$(curl -s --max-time 120 -X POST "$BASE_URL/v1/messages" \
  -H "content-type: application/json" \
  -H "x-api-key: $CC_KEY" \
  -H "anthropic-version: 2023-06-01" \
  -d '{
    "model": "step-3-5-flash",
    "max_tokens": 200,
    "messages": [{"role": "user", "content": "Read /tmp/test.txt"}],
    "stream": false,
    "tools": [
      {
        "name": "Read",
        "description": "Read a file",
        "input_schema": {
          "type": "object",
          "properties": {
            "filePath": {"type": "string", "description": "path to file"}
          },
          "required": ["filePath"]
        }
      }
    ],
    "tool_choice": {"type": "auto"}
  }' 2>/dev/null)

check_contains "返回 stop_reason" "stop_reason" "$TOOL_ANTH_RESP"
check_contains "返回 tool_use" "tool_use" "$TOOL_ANTH_RESP" || \
  check_contains "返回 text" "text" "$TOOL_ANTH_RESP"
echo ""

# ============== 6. Anthropic 多轮工具调用 ==============
echo "--- 6. Anthropic 多轮工具调用 (tool_result) ---"

MULTI_ANTH_RESP=$(curl -s --max-time 120 -X POST "$BASE_URL/v1/messages" \
  -H "content-type: application/json" \
  -H "x-api-key: $CC_KEY" \
  -H "anthropic-version: 2023-06-01" \
  -d '{
    "model": "step-3-5-flash",
    "max_tokens": 200,
    "messages": [
      {"role": "user", "content": "What was in /tmp/test.txt?"},
      {"role": "assistant", "content": [
        {"type": "text", "text": "Let me read it."},
        {"type": "tool_use", "id": "tu_abc123", "name": "Read", "input": {"filePath": "/tmp/test.txt"}}
      ]},
      {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": "tu_abc123", "content": "Hello World"}
      ]}
    ],
    "stream": false,
    "tools": [
      {
        "name": "Read",
        "description": "Read a file",
        "input_schema": {
          "type": "object",
          "properties": {
            "filePath": {"type": "string", "description": "path to file"}
          },
          "required": ["filePath"]
        }
      }
    ]
  }' 2>/dev/null)

check_contains "多轮工具调用返回 stop_reason" "stop_reason" "$MULTI_ANTH_RESP"

echo ""
echo "=========================================="
echo " 测试结果: $PASS 通过, $FAIL 失败"
echo "=========================================="

if [ "$FAIL" -gt 0 ]; then
    exit 1
fi
