import json
from pathlib import Path

import pytest

from boss.redact import MASK, redact, safe_text

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


@pytest.mark.parametrize(
    "text",
    [
        "task-abcdefghijklmnopqrstuvwxyz",  # B48: a word ending in sk, then 20+ letters
        "see disk-ImageConfigurationManagement for it",
        "desk-" + "0123456789abcdef" * 2,
        "ask-" + "A" * 26,
        "sk-learn-pipeline-configuration-notes",  # hyphen body, no digit or case mix
        "max_tokens: 1000000",  # B48
        "max_tokens=4096",
        "input_tokens: 123456",
        "token_count = 1234567",
        "maxTokens: 1,000,000",
        "TOKENS_USED=12345678",
    ],
)
def test_lookalikes_of_a_key_or_a_secret_assignment_are_untouched(text):
    assert redact(text) == text


@pytest.mark.parametrize(
    ("text", "masked"),
    [
        ("task" + SAMPLES["openai project key"], True),
        ("disk-" + "aB3" * 16, True),  # key-like body wins over a vowel before sk
        ("id: sk-" + "a" * 30, True),
        ("sk-" + "aB3-" * 8, True),  # unknown vendor segment, key-like body
        ("sk-or-v1-" + "0123456789abcdef" * 4, True),
        ("sk-None-" + "aB3" * 16, True),
        ("TOKEN=1234567890", True),  # a bare token that is only digits is still a secret
        ("API_TOKEN: 1234567", True),
        ("max_tokens: abcdefgh12345", True),  # a count name does not excuse a non-number
        ("max_tokens: 1000000x", True),
        ("PASSWORD=12345678", True),
        ("SECRET_TOKENS=sk_live_abcdef", True),
    ],
)
def test_the_lookalike_rules_do_not_let_a_real_secret_through(text, masked):
    assert (MASK in redact(text)) is masked


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


@pytest.mark.parametrize(
    ("raw", "shown"),
    [
        ("\x1b[31mred\x1b[0m", "\\x1b[31mred\\x1b[0m"),
        ("bell\x07 nul\x00 cr\r del\x7f", "bell\\x07 nul\\x00 cr\\x0d del\\x7f"),
        ("csi\x9b31m and \x80\x9f", "csi\\x9b31m and \\x80\\x9f"),
    ],
)
def test_safe_text_makes_control_characters_visible(raw, shown):
    assert safe_text(raw) == shown


def test_safe_text_keeps_newline_tab_and_ordinary_unicode():
    assert safe_text("a\tb\nc \u00e9\u4e2d\u00a0") == "a\tb\nc \u00e9\u4e2d\u00a0"


def test_safe_text_masks_secrets_and_known_values():
    key = "sk-ant-" + "a" * 30
    assert safe_text(
        f"k={key} v=plain-looking-9f8e7d", known_secrets=("plain-looking-9f8e7d",)
    ) == (f"k={MASK} v={MASK}")


def test_safe_text_without_limit_never_cuts():
    assert safe_text("x" * 100_000) == "x" * 100_000


def test_safe_text_cuts_to_the_limit_with_a_marker():
    out = safe_text("x" * 100, limit=30)
    assert len(out) == 30
    assert out == "x" * 24 + " [cut]"
    assert safe_text("x" * 30, limit=30) == "x" * 30  # exactly at the limit is not cut


def test_safe_text_rejects_a_limit_too_small_for_the_marker():
    with pytest.raises(ValueError, match="limit"):
        safe_text("anything", limit=3)


def test_safe_text_second_redaction_can_not_push_it_past_the_limit():
    # Cutting inside "[REDACTED]" leaves "[REDAC", which the env-style pattern re-masks to the
    # full ten characters, so the cut text grows by four.
    out = safe_text("API_KEY=abcdefghij tail tail tail", limit=20)
    assert len(out) <= 20
    assert out.endswith(" [cut]")


@pytest.mark.parametrize("offset", range(150, 200, 3))
def test_safe_text_never_half_reveals_a_secret_across_the_cut(offset):
    secret = "ghp_" + "Ab3" * 12
    text = "x" * offset + secret + "y" * 100
    out = safe_text(text, limit=190)
    assert len(out) <= 190
    assert "ghp_" not in out
    assert secret[:12] not in out


@pytest.mark.parametrize("limit", [None, 12, 20, 200])
def test_safe_text_is_idempotent(limit):
    text = (
        "\x1b[2Jhead API_KEY=abcdefghij http://a:b@h/ Bearer " + "q" * 30 + "\x00" * 5 + "z" * 300
    )
    once = safe_text(text, limit=limit)
    assert safe_text(once, limit=limit) == once
