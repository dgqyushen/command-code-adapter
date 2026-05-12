from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

REASONING_EFFORT_MAX = (
    "Reasoning Effort: Absolute maximum with no shortcuts permitted.\n"
    "You MUST be very thorough in your thinking and comprehensively decompose "
    "the problem to resolve the root cause, rigorously stress-testing your "
    "logic against all potential paths, edge cases, and adversarial scenarios.\n"
    "Explicitly write out your entire deliberation process, documenting every "
    "intermediate step, considered alternative, and rejected hypothesis to "
    "ensure absolutely no assumption is left unchecked.\n\n"
)

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

REASONING_EFFORT_MAP: dict[str, str] = {
    "off": "Respond directly without showing step-by-step reasoning.",
    "low": "Be concise. Minimize step-by-step reasoning.",
    "medium": "",
    "high": "Think step-by-step and show your reasoning process.",
    "xhigh": "Think carefully step-by-step. Show detailed reasoning.",
    "max": "Think very thoroughly. Show exhaustive step-by-step reasoning with detailed analysis.",
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
