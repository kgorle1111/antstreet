"""Redaction edge cases: overlapping secrets, repeated passes, and shapes the patterns miss."""

import time

import pytest

from antstreet.redact import MASK, redact, safe_text

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


@pytest.mark.parametrize("key", ["password", "api_key", "client_secret"])
def test_json_style_secret_values_are_masked(key):
    assert "hunter2222" not in redact(f'{{"{key}": "hunter2222"}}')


def test_private_key_block_cut_off_before_its_end_line_is_masked():
    assert "MIIEvQIBADANBgkq" not in redact("-----BEGIN PRIVATE KEY-----\nMIIEvQIBADANBgkq\nabc")


def test_a_quoted_key_keeps_its_name_and_loses_only_its_value():
    assert redact('{"api_key": "abcdef123456", "name": "visible"}') == (
        f'{{"api_key": "{MASK}", "name": "visible"}}'
    )
    assert redact("{'client_secret' : 'two words here'}") == f"{{'client_secret' : '{MASK}'}}"


def test_a_quoted_key_that_is_not_a_secret_name_is_left_alone():
    text = '{"status": "continuing", "reason": "wrote rev.py", "tokens": 120000}'
    assert redact(text) == text


def test_private_key_block_cut_off_before_its_end_line_is_masked_to_the_end_only():
    text = "before\n-----BEGIN RSA PRIVATE KEY-----\nMIIEvQIBADANBgkq\nabc"
    assert redact(text) == f"before\n{MASK}"


def test_private_key_block_whose_begin_line_was_cut_off_is_masked():
    # The gate keeps only the tail of the output, so a block can arrive headless.
    text = "BADANBgkq\nMIIEvQIBADANBgkq+/==\n-----END PRIVATE KEY-----\nafter the key"
    assert redact(text) == f"{MASK}\nafter the key"
    prose = "this line has spaces, so it is not key material\nQUJD\n-----END PRIVATE KEY-----"
    assert redact(prose) == f"this line has spaces, so it is not key material\n{MASK}"


def test_a_complete_key_block_is_masked_once_and_the_text_around_it_kept():
    block = "-----BEGIN PRIVATE KEY-----\nQUJD\n-----END PRIVATE KEY-----"
    assert redact(f"a\n{block}\nb\n{block}\nc") == f"a\n{MASK}\nb\n{MASK}\nc"


# Found by review: the first version of the headless-key rule was a regex with a repeated line
# group. 1 MB of key-like lines with no END line took 70 seconds, and a worker's status text
# reaches this code, so a worker could stall the loop.
@pytest.mark.parametrize(
    "text",
    [
        ("A" * 64 + "\n") * 16_000,  # about 1 MB of key-like lines, no END line
        "AB\n" * 33_000,
        ("A" * 64 + "\n") * 8_000 + "not key material\n" + ("B" * 64 + "\n") * 8_000,
        "-----BEGIN PRIVATE KEY-----\n" * 5_000,
        "-----END PRIVATE KEY-----\n" * 5_000,
        "sk-" * 100_000,
        "ab-" * 100_000,  # scheme characters with no ://, retried from every word boundary
        "task-" * 60_000,
        "password=" * 50_000,
        "'" * 200_000,
    ],
    ids=[
        "key-lines",
        "short-lines",
        "two-runs",
        "many-begins",
        "many-ends",
        "sk",
        "scheme-run",
        "task-run",
        "assign",
        "quotes",
    ],
)
def test_redaction_is_fast_on_adversarial_input(text):
    started = time.perf_counter()
    redact(text)
    assert time.perf_counter() - started < 2.0


def test_every_headless_block_is_masked_and_the_text_between_them_kept():
    text = "QUJD\n-----END PRIVATE KEY-----\nkeep me\nREVG\nR0hJ\n-----END RSA PRIVATE KEY-----\n"
    assert redact(text) == f"{MASK}\nkeep me\n{MASK}\n"


def test_a_headless_block_at_the_very_start_and_crlf_lines_are_masked():
    assert redact("-----END PRIVATE KEY-----") == MASK
    assert redact("QUJD\r\nREVG\r\n-----END PRIVATE KEY-----") == MASK


def test_key_material_lines_stop_at_the_first_line_that_is_not_key_material():
    text = "QUJD\n\nREVG\n-----END PRIVATE KEY-----"  # a blank line ends the block
    assert redact(text) == f"QUJD\n\n{MASK}"


def test_safe_text_with_a_limit_does_not_read_a_huge_input_to_the_end():
    huge = "ok " + ("A" * 64 + "\n") * 200_000  # 13 MB
    started = time.perf_counter()
    assert safe_text(huge, limit=50).startswith("ok AAAA")
    assert time.perf_counter() - started < 1.0


def test_a_secret_beyond_the_limit_never_appears_and_one_across_it_is_not_half_shown():
    secret = "sk-ant-" + "z" * 40
    assert secret[:20] not in safe_text("x" * 40 + secret, limit=50)
    assert "zzz" not in safe_text("x" * 5_000 + secret, limit=50)


@pytest.mark.parametrize("char", ["\u202e", "\u200b", "\u2066", "\ufeff", "\u200f"])
def test_invisible_format_characters_are_made_visible(char):
    shown = safe_text(f"safe{char}text")
    assert char not in shown and f"\\u{ord(char):04x}" in shown


def test_key_material_glued_to_the_end_of_an_earlier_block_is_masked_with_the_next():
    text = "-----END PRIVATE KEY-----QUJD\n-----END PRIVATE KEY-----"
    assert redact(text) == MASK + MASK
