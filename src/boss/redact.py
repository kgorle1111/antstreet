"""Remove credentials from text before it is written to any log or shown in a report."""

from __future__ import annotations

import re
from collections.abc import Iterable

MASK = "[REDACTED]"
_MIN_KNOWN_SECRET_LEN = 8  # shorter values would mask ordinary words

_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S),
        MASK,
    ),
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
