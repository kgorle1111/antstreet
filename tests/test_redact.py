import json
from pathlib import Path

import pytest

from boss.redact import MASK, redact

# Fake values shaped like real credentials. None of these are live.
SAMPLES = {
    "anthropic key": "sk-ant-api03-" + "A1b2C3d4E5f6G7h8I9j0" * 2,
    "claude oauth token": "sk-ant-oat01-" + "Zz9Yy8Xx7Ww6Vv5Uu4Tt" * 2,
    "openai project key": "sk-proj-" + "abcDEF123ghiJKL456mno",
    "github token": "ghp_" + "a" * 36,
    "github fine-grained": "github_pat_" + "B" * 30,
    "aws key id": "AKIA" + "ABCDEFGHIJKLMNOP",
    "slack token": "xoxb-" + "123456789012-abcdefghij",
    "jwt": "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTYifQ.c2lnbmF0dXJlX3ZhbHVl",
}


@pytest.mark.parametrize("secret", SAMPLES.values(), ids=SAMPLES.keys())
def test_credential_shapes_are_masked_and_context_kept(secret):
    out = redact(f"before {secret} after")
    assert secret not in out
    assert out == f"before {MASK} after"


def test_bearer_header_keeps_scheme():
    assert redact("Authorization: Bearer abcdefghijklmnop1234") == f"Authorization: Bearer {MASK}"


def test_url_credentials():
    out = redact("postgres://admin:s3cretpass@db.example.com:5432/app")
    assert out == f"postgres://{MASK}@db.example.com:5432/app"


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("ANTHROPIC_API_KEY=abc123xyz789", f"ANTHROPIC_API_KEY={MASK}"),
        ('db_password: "hunter2hunter2"', f'db_password: "{MASK}"'),
        ("GITHUB_TOKEN = 'tok_value_here'", f"GITHUB_TOKEN = '{MASK}'"),
    ],
)
def test_env_style_assignments(line, expected):
    assert redact(line) == expected


def test_private_key_block():
    block = "-----BEGIN RSA PRIVATE KEY-----\nMIIEow\nabc\n-----END RSA PRIVATE KEY-----"
    assert redact(f"key:\n{block}\nend") == f"key:\n{MASK}\nend"


def test_known_secret_values_are_masked_whatever_their_shape():
    assert redact("value is plain-looking-9f8e7d", known_secrets=["plain-looking-9f8e7d"]) == (
        f"value is {MASK}"
    )


def test_short_known_values_are_ignored_to_avoid_masking_words():
    assert redact("the cat sat", known_secrets=["cat"]) == "the cat sat"


@pytest.mark.parametrize(
    "text",
    [
        "skeleton key and task-ant are ordinary words",
        "Bearer of good news",
        "token budget: 1500 tokens used",
        "the password field is required",
        "https://example.com/path?x=1",
        "sk-short",
    ],
)
def test_ordinary_text_is_untouched(text):
    assert redact(text) == text


def test_recorded_fixtures_need_no_redaction():
    # Over-redaction would corrupt worker logs; the sanitized probe recordings must pass through.
    for path in sorted((Path(__file__).parent / "fixtures").iterdir()):
        text = path.read_text()
        assert redact(text) == text, path.name


def test_redacted_json_line_stays_valid_json():
    line = json.dumps({"cmd": "curl -H 'Authorization: Bearer abcdefghijklmnop1234' x"})
    assert json.loads(redact(line))["cmd"] == f"curl -H 'Authorization: Bearer {MASK}' x"


@pytest.mark.parametrize(
    ("before", "secret", "after"),
    [
        ("x", "sk-ant-" + "a" * 30, ""),
        ("x", "sk-" + "a" * 30, ""),
        ("x", "ghp_" + "a" * 36, ""),
        ("x", "AKIA" + "A" * 16, ""),
        ("", "AKIA" + "A" * 16, "x"),
        ("x", "xoxb-" + "1" * 12, ""),
        ("x", SAMPLES["jwt"], ""),
    ],
)
def test_secret_glued_to_surrounding_text_is_masked(before, secret, after):
    assert redact(before + secret + after) == before + MASK + after


def test_bearer_glued_to_a_preceding_word_is_masked():
    assert redact("xBearer " + "a" * 24) == f"xBearer {MASK}"


@pytest.mark.parametrize(
    "text",
    [
        "taskbar",
        "risk-antics and ask-anthony",
        "makiage and a MAKIAVELLI note",
        "task-runner-configuration-file-loader",  # bare sk- with a hyphenated body
        "AKIA plus a short tail",
        "ghp_ short and ghost_pipeline",
        "sunbasic nothing here",
    ],
)
def test_words_that_merely_contain_a_prefix_are_untouched(text):
    assert redact(text) == text
