from browsermcp.redact import redact


def test_email_masked():
    assert redact("contact me at john.doe@example.com today") == "contact me at <email> today"


def test_multiple_emails_masked():
    result = redact("first user1@a.co and second user2+tag@b.io")
    assert "user1@a.co" not in result
    assert "user2+tag@b.io" not in result
    assert result.count("<email>") == 2


def test_phone_masked():
    assert redact("call 415-555-1234 please") == "call <phone> please"
    assert redact("call 415.555.1234 please") == "call <phone> please"
    assert redact("call 4155551234 please") == "call <phone> please"


def test_ssn_masked():
    assert redact("ssn 123-45-6789 here") == "ssn <ssn> here"


def test_credit_card_masked():
    assert redact("card 4111 1111 1111 1111 end") == "card <cc> end"
    assert redact("card 4111-1111-1111-1111 end") == "card <cc> end"


def test_field_name_redaction_password():
    out = redact({"username": "alice", "password": "hunter2"})
    assert out["username"] == "alice"
    assert out["password"] == "<redacted>"


def test_field_name_redaction_case_insensitive():
    out = redact({"Password": "x", "SECRET": "y", "Token": "z", "DOB": "1990-01-01"})
    assert out["Password"] == "<redacted>"
    assert out["SECRET"] == "<redacted>"
    assert out["Token"] == "<redacted>"
    assert out["DOB"] == "<redacted>"


def test_field_name_redaction_ssn_key():
    out = redact({"ssn": "anything-goes"})
    assert out["ssn"] == "<redacted>"


def test_nested_dict_redacted():
    payload = {
        "user": {
            "email": "a@b.com",
            "password": "secretpw",
            "profile": {"phone": "415-555-1234"},
        }
    }
    out = redact(payload)
    assert out["user"]["email"] == "<email>"
    assert out["user"]["password"] == "<redacted>"
    assert out["user"]["profile"]["phone"] == "<phone>"


def test_list_of_dicts_redacted():
    payload = [{"email": "a@b.com"}, {"phone": "415-555-1234"}]
    out = redact(payload)
    assert out[0]["email"] == "<email>"
    assert out[1]["phone"] == "<phone>"


def test_mixed_list_redacted():
    out = redact(["plain text", "email a@b.com", {"password": "p"}])
    assert out[0] == "plain text"
    assert out[1] == "email <email>"
    assert out[2]["password"] == "<redacted>"


def test_non_string_scalars_passthrough():
    assert redact(42) == 42
    assert redact(3.14) == 3.14
    assert redact(True) is True
    assert redact(None) is None


def test_returns_copy_not_mutating_input():
    original = {"email": "a@b.com", "password": "p"}
    snapshot = dict(original)
    redact(original)
    assert original == snapshot


def test_empty_containers():
    assert redact({}) == {}
    assert redact([]) == []
    assert redact("") == ""
