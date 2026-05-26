from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)


class RequestLogger:
    def __init__(self, log_dir: str = "logs"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def start_request(
        self,
        model: str,
        stream: bool,
        messages_count: int,
        body_json: str,
        system_info: str = "",
        tools_count: int = 0,
    ) -> tuple[str, Path]:
        request_id = uuid.uuid4().hex[:16]
        timestamp = datetime.now(timezone.utc)
        ts_str = timestamp.strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"{ts_str}_{request_id[:8]}.log"
        filepath = self.log_dir / filename

        header = (
            f"=== REQUEST {timestamp.isoformat()} ===\n"
            f"Request ID: {request_id}\n"
            f"Model: {model}\n"
            f"Stream: {stream}\n"
            f"Messages: {messages_count}\n"
            f"Tools: {tools_count}\n"
            f"System: {system_info}\n"
            f"--- RAW BODY ---\n"
            f"{body_json}\n"
            f"\n=== RESPONSE STREAM ===\n"
        )
        filepath.write_text(header, encoding="utf-8")

        logger.info(
            "passthrough.request.start",
            request_id=request_id,
            file=str(filepath),
            model=model,
            stream=stream,
            messages_count=messages_count,
            tools_count=tools_count,
        )

        return request_id, filepath

    def log_raw_sse(self, filepath: Path, line: str):
        with open(filepath, "a", encoding="utf-8") as f:
            f.write(f"RAW: {line}\n")

    def log_sse_event(self, filepath: Path, event_type: str, data: dict, elapsed_s: float):
        ts = f"+{elapsed_s:.1f}s"
        entry = f"[{ts}] {event_type:<24s}"

        if event_type == "content_block_delta" and isinstance(data, dict):
            delta = data.get("delta", {})
            idx = data.get("index", "?")
            text = delta.get("text", "")
            entry += f" index={idx} text={json.dumps(text)}"
        elif event_type == "message_start" and isinstance(data, dict):
            msg = data.get("message", {})
            entry += f" id={msg.get('id', '?')}"
        elif event_type == "message_delta" and isinstance(data, dict):
            delta_data = data.get("delta", {})
            entry += f" stop={delta_data.get('stop_reason', '?')}"
            usage = data.get("usage", {})
            if usage:
                entry += f" in={usage.get('input_tokens', 0)} out={usage.get('output_tokens', 0)}"
        elif event_type == "ping":
            entry += "(heartbeat)"
        elif event_type == "error":
            entry += f" error={json.dumps(data)}"

        with open(filepath, "a", encoding="utf-8") as f:
            f.write(f"{entry}\n")

    def end_request(
        self,
        filepath: Path,
        request_id: str,
        start_time: float,
        stop_reason: str = "",
        input_tokens: int = 0,
        output_tokens: int = 0,
    ):
        duration = time.monotonic() - start_time
        summary = (
            f"\n=== SUMMARY ===\n"
            f"Duration: {duration:.1f}s\n"
            f"Stop reason: {stop_reason or 'N/A'}\n"
            f"Usage: input={input_tokens} output={output_tokens}\n"
            f"Status: OK\n"
        )
        with open(filepath, "a", encoding="utf-8") as f:
            f.write(summary)

        logger.info(
            "passthrough.request.end",
            request_id=request_id,
            duration=f"{duration:.1f}s",
            stop_reason=stop_reason,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

    def end_request_error(self, filepath: Path, request_id: str, error: str, start_time: float):
        duration = time.monotonic() - start_time
        summary = (
            f"\n=== SUMMARY ===\n"
            f"Duration: {duration:.1f}s\n"
            f"Status: ERROR\n"
            f"Error: {error}\n"
        )
        with open(filepath, "a", encoding="utf-8") as f:
            f.write(summary)

        logger.warning(
            "passthrough.request.error",
            request_id=request_id,
            duration=f"{duration:.1f}s",
            error=error,
        )
