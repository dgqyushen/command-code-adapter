from cc_adapter.admin.auth import set_password, validate_token, generate_token


def test_no_password_always_valid():
    set_password("")
    token = "anything"
    assert validate_token(token) is True


def test_with_password_requires_matching_token():
    set_password("mysecret")
    token = generate_token()
    assert validate_token(token) is True
    assert validate_token("wrong") is False


def test_generate_token_returns_hex():
    set_password("pw")
    token = generate_token()
    assert len(token) == 64  # 32 bytes hex
    assert all(c in "0123456789abcdef" for c in token)
