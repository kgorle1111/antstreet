"""Redaction edge cases: overlapping secrets, repeated passes, and shapes the patterns miss."""

import pytest

from boss.redact import MASK, redact

KEY = "sk-ant-api03-" + "A1b2C3d4E5f6G7h8I9j0" * 2


def test_redaction_is_idempotent():
    text = f"ANTHROPIC_API_KEY={KEY} and Bearer abcdefghijklmnop1234 at https://u:pw12345@h/x"
    once = redact(text, known_secrets=["plain-looking-9f8e7d"])
    assert redact(once) == once
    assert KEY not in once


def test_every_secret_in_a_line_is_masked():
    out = redact(f"a={KEY} b=ghp_{'x' * 36} c=AKIA{'A' * 16}")
    assert out == f"a={MASK} b={MASK} c={MASK}"


def test_longest_known_secret_is_masked_first_so_no_tail_is_left_behind():
    out = redact("v=abcdefgh-ijklmnop end", known_secrets=["abcdefgh", "abcdefgh-ijklmnop"])
    assert out == f"v={MASK} end"


def test_known_secrets_may_be_a_generator_and_repeat():
    secrets = (s for s in ["plain-secret-1", "plain-secret-1", ""])
    assert (
        redact("x plain-secret-1 y plain-secret-1", known_secrets=secrets) == f"x {MASK} y {MASK}"
    )


def test_known_secret_with_regex_metacharacters_is_matched_literally():
    assert redact("t=a.b*c+d(e)[f]", known_secrets=["a.b*c+d(e)[f]"]) == f"t={MASK}"
    assert redact("t=aXbbbc+d(e)[f]", known_secrets=["a.b*c+d(e)[f]"]) == "t=aXbbbc+d(e)[f]"


def test_known_secret_of_exactly_the_minimum_length_is_masked():
    assert redact("k=12345678", known_secrets=["12345678"]) == f"k={MASK}"
    assert redact("k=1234567", known_secrets=["1234567"]) == "k=1234567"


@pytest.mark.parametrize("name", ["api_key", "API_KEY", "Client_Secret", "PASSWD"])
def test_assignment_names_are_matched_case_insensitively(name):
    assert redact(f"{name}=abcdef123456") == f"{name}={MASK}"


def test_assignment_values_under_six_chars_are_left_alone():
    assert redact("password=abc12") == "password=abc12"
    assert redact("password=abc123") == f"password={MASK}"


def test_basic_auth_header_keeps_its_scheme():
    assert redact("Authorization: Basic dXNlcjpwYXNzd29yZDEyMw==") == f"Authorization: Basic {MASK}"


def test_url_credentials_are_masked_for_any_scheme():
    assert redact("git+https://bot:hunter22@example.com/r.git") == (
        f"git+https://{MASK}@example.com/r.git"
    )


def test_multiline_text_is_handled_per_line():
    text = f"line one\nTOKEN={KEY}\nline three"
    assert redact(text) == f"line one\nTOKEN={MASK}\nline three"


def test_empty_text_and_no_secrets():
    assert redact("") == ""
    assert redact("", known_secrets=["abcdefghij"]) == ""


@pytest.mark.xfail(
    strict=True,
    reason="redact.py: the assignment pattern needs the name directly before = or :, "
    "so a quoted JSON key leaks its value",
)
@pytest.mark.parametrize("key", ["password", "api_key", "client_secret"])
def test_json_style_secret_values_are_masked(key):
    assert "hunter2222" not in redact(f'{{"{key}": "hunter2222"}}')


@pytest.mark.xfail(
    strict=True,
    reason="redact.py: a private key block with no END line (a truncated log) is not matched",
)
def test_private_key_block_cut_off_before_its_end_line_is_masked():
    assert "MIIEvQIBADANBgkq" not in redact("-----BEGIN PRIVATE KEY-----\nMIIEvQIBADANBgkq\nabc")
