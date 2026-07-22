"""Stateless derivation of upstream session id and x-project-slug.

The upstream cmd CLI derives a per-process `sess_<16 hex>` id on startup and
keeps it stable for the process lifetime. The adapter can not imitate that
verbatim (it is a long-running server, not a short-lived CLI) without leaking
signals (one session id covering many distinct end-users).

Instead we derive both the upstream session id and the project slug from a
deterministic function of the inbound request and the chosen cmd key:

    fig          = sha256(stable_flag | cmd_key)
    session_id   = "sess_" + fig.hex()[:16]        # matches cmd CLI shape
    project_slug = POOL[fig uint32 % len(POOL)]    # looks like a real cwd slug

This makes every (stable_flag, cmd_key) pair land on a unique (session_id,
slug) tuple with no in-memory state. Switching cmd keys invalidates the
session id, which is the correct behavior: each cmd key is a different
upstream account and must not share session-scoped state.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any


# Pool of plausible project slugs (lowercase, hyphenated, cwd-style).
# Sized so that a 16-element pool gives ~4 bits of spread per slug.
_PROJECT_SLUG_POOL: tuple[str, ...] = (
    "alpha-services",
    "analytics-pipeline",
    "auth-gateway",
    "checkout-service",
    "core-api",
    "data-platform",
    "edge-runtime",
    "frontend-app",
    "infra-automation",
    "ml-training",
    "notification-hub",
    "payment-service",
    "search-indexer",
    "storage-layer",
    "user-portal",
    "video-pipeline",
)

_CMD_SESSION_PATTERN = re.compile(r"^sess_[0-9a-f]{16}$")


def is_valid_cmd_session_id(value: str) -> bool:
    """True if value matches cmd CLI's per-process session id shape."""
    if not isinstance(value, str) or len(value) != 21:
        return False
    return bool(_CMD_SESSION_PATTERN.match(value))


class SessionExtractor:
    """Stateless extractor: request -> (stable_flag, session_id, project_slug)."""

    _POOL_SIZE = len(_PROJECT_SLUG_POOL)

    def extract_stable_flag(self, body: Any, headers: dict[str, str] | None) -> str:
        """Return a string that is stable across all turns of one conversation
        and differs across distinct conversations.

        Mirrors CLIProxyAPI's extractSessionIDs priority list, omitting sources
        that are not available inside the CC body format (metadata.user_id,
        conversation_id).

        Priority:
            1. X-Session-ID / session-id / session_id header
            2. X-Client-Request-Id header (PI-style)
            3. content hash of system + first user message (always available)
        """
        headers = headers or {}

        # 1. session headers (CLIProxyAPI priorities 2 & 3)
        for name in ("x-session-id", "session-id", "session_id"):
            if value := headers.get(name):
                return f"header:{value}"

        # 2. X-Client-Request-Id (CLIProxyAPI priority 4)
        if value := headers.get("x-client-request-id"):
            return f"clientreq:{value}"

        # 3. content hash fallback (CLIProxyAPI priority 7)
        if isinstance(body, dict):
            return f"msg:{self._content_hash(body)}"
        return "msg:empty"

    def derive(self, stable_flag: str, cmd_key: str) -> tuple[str, str]:
        """Return (session_id, project_slug) for a (stable_flag, cmd_key) pair.

        Pure function: same inputs always yield the same outputs.
        """
        if not isinstance(stable_flag, str) or not stable_flag:
            raise ValueError("stable_flag must be a non-empty string")
        if not isinstance(cmd_key, str) or not cmd_key:
            raise ValueError("cmd_key must be a non-empty string")

        digest = hashlib.sha256(f"{stable_flag}|{cmd_key}".encode()).digest()
        session_id = f"sess_{digest.hex()[:16]}"
        slug = _PROJECT_SLUG_POOL[int.from_bytes(digest[:4], "big") % self._POOL_SIZE]
        return session_id, slug

    def _content_hash(self, body: dict) -> str:
        """Hash system + first user message (truncated to 100 chars each).

        The adapter sends a CC body ({..., params: {system, messages, ...}}) to
        the upstream. System and messages live inside *params*, not at the
        top level.

        Anchors are chosen so the hash is identical across every turn of one
        conversation: system prompt is stable, and only the first user message
        is taken (later user turns and assistant replies do not contribute).
        """
        params = body.get("params") if isinstance(body, dict) else {}
        if not isinstance(params, dict):
            params = {}
        h = hashlib.sha256()
        h.update(f"sys:{self._first_text(params.get('system'))[:100]}\n".encode())
        user_text = self._first_text_from_role(params.get("messages", []), "user")
        if user_text:
            h.update(f"usr:{user_text[:100]}\n".encode())
        return h.hexdigest()[:16]

    @staticmethod
    def _first_text(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        if isinstance(value, list):
            parts: list[str] = []
            for item in value:
                if isinstance(item, dict):
                    text = item.get("text")
                    if isinstance(text, str):
                        parts.append(text)
                elif isinstance(item, str):
                    parts.append(item)
            return " ".join(parts)
        return str(value)

    @staticmethod
    def _first_text_from_role(messages: Any, role: str) -> str:
        if not isinstance(messages, list):
            return ""
        for msg in messages:
            if isinstance(msg, dict) and msg.get("role") == role:
                return SessionExtractor._first_text(msg.get("content"))
        return ""


_SESSION_EXTRACTOR: SessionExtractor | None = None


def get_session_extractor() -> SessionExtractor:
    global _SESSION_EXTRACTOR
    if _SESSION_EXTRACTOR is None:
        _SESSION_EXTRACTOR = SessionExtractor()
    return _SESSION_EXTRACTOR
