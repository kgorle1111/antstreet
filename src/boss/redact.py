"""Remove credentials from text before it is written to any log or shown in a report."""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence

MASK = "[REDACTED]"
_MIN_KNOWN_SECRET_LEN = 8  # shorter values would mask ordinary words
_CUT = " [cut]"
# C0, DEL and C1 controls except newline and tab; a raw ESC in model output could drive a terminal.
_CONTROL_ESCAPES = {
    c: f"\\x{c:02x}" for c in (*range(0x20), 0x7F, *range(0x80, 0xA0)) if c not in (0x0A, 0x09)
}

_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    # Output is cut to its tail before it gets here, so a key block can arrive without its END
    # line (masked to the end of the text) or without its BEGIN line (the key lines above the END
    # line are masked).
    (
        re.compile(
            r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?(?:-----END [A-Z ]*PRIVATE KEY-----|\Z)", re.S
        ),
        MASK,
    ),
    (re.compile(r"(?m)(?:^[A-Za-z0-9+/=]+\r?\n)*^-----END [A-Z ]*PRIVATE KEY-----"), MASK),
    # No leading \b on the prefixed shapes: gate output is cut mid-line, so a key can be glued to
    # the text before it. Bare `sk-` is too common inside words ("task-runner-...") to match there
    # unless the body is hyphen-free, so hyphenated bodies still need a word boundary.
    (
        re.compile(
            r"sk-(?:ant|proj|svcacct|admin)-[A-Za-z0-9_-]{20,}"  # Anthropic / OpenAI-style keys
            r"|(?<!\w)sk-[A-Za-z0-9_-]{20,}"
            r"|sk-[A-Za-z0-9]{20,}"
        ),
        MASK,
    ),
    (re.compile(r"(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{22,})"), MASK),
    (re.compile(r"AKIA[0-9A-Z]{16}"), MASK),  # AWS access key id
    (re.compile(r"xox[abprs]-[A-Za-z0-9-]{10,}"), MASK),  # Slack
    (re.compile(r"eyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"), MASK),  # JWT
    (re.compile(r"(?i)(bearer|basic)\s+[A-Za-z0-9._~+/=-]{16,}"), rf"\1 {MASK}"),
    (re.compile(r"(?i)(\b[a-z][a-z0-9+.-]*://)[^\s/:@]+:[^\s/@]+@"), rf"\1{MASK}@"),  # URL creds
    (  # a quoted key, as in JSON: "password": "value"
        re.compile(
            r"(?i)(['\"])([A-Z0-9_]*(?:API_?KEY|SECRET|TOKEN|PASSWORD|PASSWD)[A-Z0-9_]*)\1"
            r"(\s*:\s*)(['\"])[^'\"]{6,}\4"
        ),
        rf"\1\2\1\3\4{MASK}\4",
    ),
    (
        re.compile(
            r"(?i)\b([A-Z0-9_]*(?:API_?KEY|SECRET|TOKEN|PASSWORD|PASSWD)[A-Z0-9_]*)"
            r"(\s*[=:]\s*)(['\"]?)[^\s'\"]{6,}\3"
        ),
        rf"\1\2\3{MASK}\3",
    ),
)


def redact(text: str, known_secrets: Iterable[str] = ()) -> str:
    """Mask credential-shaped strings and the exact values in `known_secrets`.

    `known_secrets` should hold every secret value passed to a child process, so a key is masked
    even when its format is not one of the patterns.
    """
    known = {s for s in known_secrets if len(s) >= _MIN_KNOWN_SECRET_LEN}
    for secret in sorted(known, key=len, reverse=True):  # longest first, so no partial leftovers
        text = text.replace(secret, MASK)
    for pattern, replacement in _PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def safe_text(text: str, *, limit: int | None = None, known_secrets: Sequence[str] = ()) -> str:
    """`text` made safe to show a person: secrets masked, control characters made visible, and
    at most `limit` characters long, ending in ` [cut]` if it was cut.

    Redaction runs before the cut and again after it, so a secret straddling the cut is never
    half-shown. The second pass can lengthen the text (a short URL credential becomes the mask),
    hence the final re-cut. Idempotent.
    """
    if limit is not None and limit < len(_CUT):
        raise ValueError(f"limit must be at least {len(_CUT)}")

    def cut(value: str) -> str:
        if limit is None or len(value) <= limit:
            return value
        return value[: limit - len(_CUT)] + _CUT

    text = redact(text, known_secrets).translate(_CONTROL_ESCAPES)
    return cut(redact(cut(text), known_secrets))
