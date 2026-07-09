"""Tests for cc_adapter.providers.shared.session_extractor."""

import pytest

from cc_adapter.command_code.body import make_cc_body, make_config
from cc_adapter.providers.shared.session_extractor import (
    SessionExtractor,
    get_session_extractor,
    is_valid_cmd_session_id,
)


def _cc_body(**params):
    """Return a CC body as produced by request translators (system + messages
    live inside params, not at the top level)."""
    return make_cc_body(config=make_config(), params=params)


class TestSessionExtractorStableFlag:
    def setup_method(self):
        self.ex = SessionExtractor()

    def test_header_x_session_id_takes_priority(self):
        flag = self.ex.extract_stable_flag(
            _cc_body(model="m", system="sys", messages=[]),
            {"x-session-id": "abc-123"},
        )
        assert flag == "header:abc-123"

    def test_header_session_id_variant(self):
        flag = self.ex.extract_stable_flag(
            _cc_body(model="m", system="sys", messages=[]),
            {"session_id": "sid-1"},
        )
        assert flag == "header:sid-1"

    def test_header_x_client_request_id(self):
        flag = self.ex.extract_stable_flag(
            _cc_body(model="m", system="sys", messages=[]),
            {"x-client-request-id": "req-42"},
        )
        assert flag == "clientreq:req-42"

    def test_fallback_to_content_hash(self):
        flag = self.ex.extract_stable_flag(
            _cc_body(
                model="m",
                system="You are a helpful assistant.",
                messages=[{"role": "user", "content": "hello"}],
            ),
            {},
        )
        assert flag.startswith("msg:")
        assert len(flag) == len("msg:") + 16

    def test_fallback_when_body_is_not_dict(self):
        flag = self.ex.extract_stable_flag(None, {})
        assert flag == "msg:empty"

    def test_content_hash_stable_across_turns(self):
        """More turns must not change the hash — system + first user anchor."""
        base = _cc_body(
            model="m",
            system="sys",
            messages=[{"role": "user", "content": "first ask"}],
        )
        extended = _cc_body(
            model="m",
            system="sys",
            messages=[
                {"role": "user", "content": "first ask"},
                {"role": "assistant", "content": "first answer"},
                {"role": "user", "content": "follow up question"},
            ],
        )
        assert self.ex.extract_stable_flag(base, {}) == self.ex.extract_stable_flag(extended, {})

    def test_content_diff_changes_hash(self):
        a = self.ex.extract_stable_flag(
            _cc_body(model="m", system="A", messages=[{"role": "user", "content": "x"}]),
            {},
        )
        b = self.ex.extract_stable_flag(
            _cc_body(model="m", system="B", messages=[{"role": "user", "content": "x"}]),
            {},
        )
        assert a != b

    def test_content_hash_different_users_diverge(self):
        a = self.ex.extract_stable_flag(
            _cc_body(model="m", system="sys", messages=[{"role": "user", "content": "ask A"}]),
            {},
        )
        b = self.ex.extract_stable_flag(
            _cc_body(model="m", system="sys", messages=[{"role": "user", "content": "ask B"}]),
            {},
        )
        assert a != b

    def test_content_hash_handles_string_system(self):
        flag = self.ex.extract_stable_flag(
            _cc_body(
                model="m",
                system="system prompt",
                messages=[{"role": "user", "content": "hi"}],
            ),
            {},
        )
        assert flag.startswith("msg:")

    def test_content_hash_handles_list_system(self):
        flag = self.ex.extract_stable_flag(
            _cc_body(
                model="m",
                system=[{"type": "text", "text": "system prompt"}],
                messages=[{"role": "user", "content": "hi"}],
            ),
            {},
        )
        assert flag.startswith("msg:")

    def test_content_hash_handles_string_content(self):
        flag = self.ex.extract_stable_flag(
            _cc_body(
                model="m",
                system="s",
                messages=[{"role": "user", "content": "plain text"}],
            ),
            {},
        )
        assert flag.startswith("msg:")

    def test_content_hash_handles_list_content(self):
        flag = self.ex.extract_stable_flag(
            _cc_body(
                model="m",
                system="s",
                messages=[{"role": "user", "content": [{"type": "text", "text": "part"}]}],
            ),
            {},
        )
        assert flag.startswith("msg:")

    def test_content_hash_handles_non_string_system(self):
        # Non-str / non-list values coerce via str().
        flag = self.ex.extract_stable_flag(
            _cc_body(model="m", system=42, messages=[]),
            {},
        )
        assert flag.startswith("msg:")

    def test_content_hash_handles_non_list_messages(self):
        # Defensive: body["params"]["messages"] might not be a list.
        flag = self.ex.extract_stable_flag(
            {"params": {"system": "s", "messages": "not-a-list"}},
            {},
        )
        assert flag.startswith("msg:")

    def test_content_hash_skips_non_user_roles(self):
        # Messages with no "user" role still hash deterministically.
        flag_a = self.ex.extract_stable_flag(
            _cc_body(model="m", system="sys", messages=[{"role": "system", "content": "sys"}]),
            {},
        )
        flag_b = self.ex.extract_stable_flag(
            _cc_body(model="m", system="sys", messages=[{"role": "tool", "content": "tool"}]),
            {},
        )
        assert flag_a == flag_b  # same sys, different non-user roles


class TestSessionExtractorDerive:
    def setup_method(self):
        self.ex = SessionExtractor()

    def test_derive_returns_cmd_compatible_session_id(self):
        session_id, slug = self.ex.derive("msg:abc123", "key1")
        assert is_valid_cmd_session_id(session_id)
        assert session_id.startswith("sess_")
        assert len(session_id) == 21

    def test_derive_returns_valid_slug(self):
        _, slug = self.ex.derive("msg:abc123", "key1")
        assert slug
        assert slug.islower()

    def test_derive_is_deterministic(self):
        a = self.ex.derive("msg:abc", "key1")
        b = self.ex.derive("msg:abc", "key1")
        assert a == b

    def test_derive_session_changes_per_key(self):
        s1, _ = self.ex.derive("msg:same", "key1")
        s2, _ = self.ex.derive("msg:same", "key2")
        assert s1 != s2

    def test_derive_slug_spreads_across_pool(self):
        slugs = {self.ex.derive(f"msg:flag{i}", "key1")[1] for i in range(64)}
        assert len(slugs) >= 8

    def test_derive_validates_empty_inputs(self):
        with pytest.raises(ValueError):
            self.ex.derive("", "key1")
        with pytest.raises(ValueError):
            self.ex.derive("msg:abc", "")

    @pytest.mark.parametrize("bad", [123, None, []])
    def test_derive_validates_non_string_inputs(self, bad):
        with pytest.raises(ValueError):
            self.ex.derive(bad, "key1")
        with pytest.raises(ValueError):
            self.ex.derive("msg:abc", bad)


class TestSessionExtractorSingleton:
    def test_get_session_extractor_returns_same_instance(self):
        a = get_session_extractor()
        b = get_session_extractor()
        assert a is b


class TestIsValidCmdSessionId:
    def test_valid_session_id(self):
        assert is_valid_cmd_session_id("sess_a1b2c3d4e5f60718") is True

    def test_wrong_length(self):
        assert is_valid_cmd_session_id("sess_abc") is False

    def test_no_prefix(self):
        assert is_valid_cmd_session_id("a1b2c3d4e5f60718xxxx") is False

    def test_uppercase_rejected(self):
        assert is_valid_cmd_session_id("sess_A1B2C3D4E5F60718") is False

    def test_empty(self):
        assert is_valid_cmd_session_id("") is False

    def test_non_string(self):
        assert is_valid_cmd_session_id(123) is False
