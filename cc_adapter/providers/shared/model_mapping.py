from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_EFFORT_ORDER = ["off", "low", "medium", "high", "xhigh", "max"]

MODEL_PROVIDER_MAP: dict[str, str] = {
    "deepseek-v4-pro": "deepseek/deepseek-v4-pro",
    "deepseek-v4-flash": "deepseek/deepseek-v4-flash",
    "kimi-k2-6": "moonshotai/Kimi-K2.6",
    "kimi-k2-5": "moonshotai/Kimi-K2.5",
    "glm-5-1": "zai-org/GLM-5.1",
    "glm-5": "zai-org/GLM-5",
    "minimax-m2-7": "MiniMaxAI/MiniMax-M2.7",
    "minimax-m2-5": "MiniMaxAI/MiniMax-M2.5",
    "qwen-3-6-max-preview": "Qwen/Qwen3.6-Max-Preview",
    "qwen-3-6-plus": "Qwen/Qwen3.6-Plus",
    "step-3-5-flash": "stepfun/Step-3.5-Flash",
}

MODEL_REASONING_EFFORTS_MAP: dict[str, list[str]] = {
    "deepseek/deepseek-v4-pro": ["high", "max"],
    "deepseek/deepseek-v4-flash": ["high", "max"],
    "claude-sonnet-4-6": ["low", "medium", "high", "xhigh", "max"],
    "claude-opus-4-7": ["low", "medium", "high", "xhigh", "max"],
    "claude-opus-4-6": ["low", "medium", "high", "xhigh", "max"],
    "claude-haiku-4-5-20251001": ["low", "medium", "high"],
    "gpt-5.5": ["low", "medium", "high", "xhigh"],
    "gpt-5.4": ["low", "medium", "high", "xhigh"],
    "gpt-5.3-codex": ["low", "medium", "high", "xhigh"],
    "gpt-5.4-mini": ["low", "medium", "high"],
    "Qwen/Qwen3.6-Max-Preview": ["low", "medium", "high"],
    "Qwen/Qwen3.6-Plus": ["low", "medium", "high"],
    "stepfun/Step-3.5-Flash": ["low", "medium", "high"],
}

NOT_SUPPORTED_PARAMS = {
    "top_p": "top_p",
    "stop": "stop",
    "n": "n",
    "presence_penalty": "presence_penalty",
    "frequency_penalty": "frequency_penalty",
    "user": "user",
    "response_format": "response_format",
}


def resolve_model_id(model_id: str) -> str:
    return MODEL_PROVIDER_MAP.get(model_id, model_id)


def clamp_reasoning_effort(model_id: str, effort: str | None) -> str | None:
    if effort is None:
        return None
    canonical = resolve_model_id(model_id)
    supported = MODEL_REASONING_EFFORTS_MAP.get(canonical)
    if supported is None:
        return None
    if effort == "off":
        return "off"
    if effort in supported:
        return effort
    try:
        effort_idx = _EFFORT_ORDER.index(effort)
    except ValueError:
        return supported[-1]
    for s in supported:
        if _EFFORT_ORDER.index(s) >= effort_idx:
            return s
    return supported[-1]


def refresh_maps(
    provider_map: dict[str, str] | None = None,
    reasoning_efforts: dict[str, list[str]] | None = None,
) -> None:
    if provider_map is not None:
        MODEL_PROVIDER_MAP.clear()
        MODEL_PROVIDER_MAP.update(provider_map)
    if reasoning_efforts is not None:
        MODEL_REASONING_EFFORTS_MAP.clear()
        MODEL_REASONING_EFFORTS_MAP.update(reasoning_efforts)
