from __future__ import annotations

CC_BASE_HEADERS: dict[str, str] = {
    "Content-Type": "application/json",
    "x-command-code-version": "0.25.2",
    "x-cli-environment": "production",
    "x-project-slug": "adapter",
    "x-internal-team-flag": "false",
    "x-taste-learning": "false",
}


def make_cc_headers(api_key: str | None = None) -> dict[str, str]:
    headers = dict(CC_BASE_HEADERS)
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers
