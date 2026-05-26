# Passthrough Logging — Design Spec

## Purpose

Research branch to observe what DeepSeek's Anthropic API returns (especially web_search results) when Claude Code sends requests through the adapter. No CC API involvement — pure passthrough proxy with detailed request/response logging.

After research is complete, the logging code will be deleted; only the log files will be retained.

## Branch

`feature/passthrough-logging` from `master` (commit `ef6e4f7`)

## Architecture

```
Claude Code → POST /v1/messages → router.py
  ├─ web_search disabled → CC translation pipeline (UNCHANGED)
  └─ web_search enabled  → DeepSeek forward + detailed logging (NEW)
```

## Changes

### New file: `cc_adapter/core/request_logger.py`

`RequestLogger` class:

- `log_dir`: `logs/` (created automatically, gitignored)
- File naming: `logs/{YYYY-MM-DD}_{HH-MM-SS}_{request_id[:8]}.log`
- Console logging: structlog.info with structured fields
- Each request gets a unique UUID `request_id`
- Methods:
  - `start_request(req: AnthropicRequest) -> str`: Creates log file, writes request summary + body JSON, logs to console. Returns `request_id`.
  - `log_sse_line(request_id: str, line: str)`: Appends raw SSE line + parsed event info to file
  - `end_request(request_id: str, result: dict)`: Writes duration, stop_reason, token usage summary
  - `end_request_error(request_id: str, error: str)`: Writes error details
- SSE parsing: extract event type, text deltas from `content_block_delta`, stop reasons, token usage from `message_delta`

### Modified: `cc_adapter/providers/anthropic/router.py`

Add logging hooks to the DeepSeek forwarding path only:

- `_stream_from_deepseek`: Create logger at start, log each SSE line, call `end_request` on completion or `end_request_error` on failure
- `_deepseek_nonstream`: Create logger at start, log full response, call `end_request`
- CC translation path (`translator.translate` branch): zero changes

## Log file format

```
=== REQUEST 2026-05-26 14:30:05.123 ===
Request ID: e3f8a1b2
Model: deepseek-v4-pro
Stream: true
Messages: 3 (tokens: ~450)
Tools: none
System prompt: yes (152 chars)
--- RAW BODY ---
{...full JSON...}

=== RESPONSE STREAM ===
[14:30:06.456 +1.3s] message_start       id=msg_01J...
[14:30:06.789 +1.7s] content_block_start  index=0 type=text
[14:30:06.890 +1.8s] content_block_delta  index=0 text="Hello"
[14:30:06.901 +1.8s] content_block_delta  index=0 text=" world!"
[14:30:07.123 +2.0s] content_block_stop   index=0
[14:30:07.234 +2.1s] message_delta        stop_reason=end_turn usage={...}
[14:30:07.345 +2.2s] message_stop

=== SUMMARY ===
Duration: 2.2s
Stop reason: end_turn
Usage: input=150 output=20
Status: OK
```

## Non-goals

- No changes to OpenAI router or responses API
- No changes to admin panel
- No new tests (this is throwaway research code)
- No Dockerfile or config changes

## Constraints

- All code in `request_logger.py` and logging hooks in `router.py` must be easy to identify and remove later
- `logs/` directory added to `.gitignore`
- Logging adds no measurable latency to passthrough forwarding
