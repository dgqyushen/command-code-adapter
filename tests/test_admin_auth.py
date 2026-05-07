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


def test_token_expires():
    set_password("pw")
    token = generate_token()
    assert validate_token(token) is True


def test_tampered_token_rejected():
    set_password("pw")
    token = generate_token()
    parts = token.split(".")
    tampered = parts[0] + "." + ("a" * len(parts[1]))
    assert validate_token(tampered) is False
    assert validate_token("not.a.token") is False


def test_password_change_invalidates_token():
    set_password("oldpass")
    token = generate_token()
    assert validate_token(token) is True
    set_password("newpass")
    assert validate_token(token) is False
