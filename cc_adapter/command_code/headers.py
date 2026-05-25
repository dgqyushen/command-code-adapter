from __future__ import annotations


def make_cc_headers(api_key: str | None = None) -> dict[str, str]:
    from cc_adapter.core.runtime import get_version_checker

    headers = {
        "Content-Type": "application/json",
        "x-command-code-version": get_version_checker().get_version(),
        "x-cli-environment": "production",
        "x-project-slug": "adapter",
        "x-internal-team-flag": "false",
        "x-taste-learning": "false",
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    from cc_adapter.core.runtime import get_config

    config = get_config()
    if config is None or config.zdr:
        headers["x-cmd-zdr"] = "1"

    return headers
