import pytest
from cc_adapter.providers.shared.model_mapping import (
    MODEL_REASONING_EFFORTS_MAP,
    clamp_reasoning_effort,
    resolve_model_id,
)


class TestClampReasoningEffort:
    def test_supported_effort_passthrough(self):
        assert clamp_reasoning_effort("deepseek/deepseek-v4-flash", "high") == "high"

    def test_unsupported_effort_clamps_up(self):
        assert clamp_reasoning_effort("deepseek/deepseek-v4-flash", "low") == "high"

    def test_unsupported_xhigh_clamps_to_max(self):
        assert clamp_reasoning_effort("deepseek/deepseek-v4-flash", "xhigh") == "max"

    def test_max_passthrough_deepseek(self):
        assert clamp_reasoning_effort("deepseek/deepseek-v4-flash", "max") == "max"

    def test_off_always_passthrough(self):
        assert clamp_reasoning_effort("deepseek/deepseek-v4-flash", "off") == "off"

    def test_model_not_in_map_returns_none(self):
        assert clamp_reasoning_effort("moonshotai/Kimi-K2.6", "high") is None

    def test_none_effort_returns_none(self):
        assert clamp_reasoning_effort("deepseek/deepseek-v4-flash", None) is None

    def test_claude_full_range_passthrough(self):
        for e in ["low", "medium", "high", "xhigh", "max"]:
            assert clamp_reasoning_effort("claude-sonnet-4-6", e) == e

    def test_gpt_mini_clamps_xhigh_to_high(self):
        assert clamp_reasoning_effort("gpt-5.4-mini", "xhigh") == "high"

    def test_model_with_alias_resolved_via_MODEL_PROVIDER_MAP(self):
        assert clamp_reasoning_effort("deepseek-v4-flash", "low") == "high"

    def test_glm_5_2_alias_resolves_to_canonical_model(self):
        assert resolve_model_id("glm-5-2") == "zai-org/GLM-5.2"

    def test_glm_5_2_supports_max_reasoning_effort(self):
        assert clamp_reasoning_effort("glm-5-2", "max") == "max"

    def test_unknown_effort_falls_back_to_max(self):
        assert clamp_reasoning_effort("deepseek/deepseek-v4-flash", "extreme") == "max"

    def test_refresh_maps_updates_reasoning_efforts(self):
        from cc_adapter.providers.shared.model_mapping import (
            MODEL_REASONING_EFFORTS_MAP,
            refresh_maps,
        )

        original = dict(MODEL_REASONING_EFFORTS_MAP)
        try:
            refresh_maps(reasoning_efforts={"test/model": ["high"]})
            assert "test/model" in MODEL_REASONING_EFFORTS_MAP
            assert MODEL_REASONING_EFFORTS_MAP["test/model"] == ["high"]
        finally:
            refresh_maps(reasoning_efforts=original)

    def test_refresh_maps_updates_provider_map(self):
        from cc_adapter.providers.shared.model_mapping import (
            MODEL_PROVIDER_MAP,
            refresh_maps,
        )

        original = dict(MODEL_PROVIDER_MAP)
        try:
            refresh_maps(provider_map={"test-short": "test/model"})
            assert "test-short" in MODEL_PROVIDER_MAP
            assert MODEL_PROVIDER_MAP["test-short"] == "test/model"
        finally:
            refresh_maps(provider_map=original)
