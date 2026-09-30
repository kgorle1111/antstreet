# Harvested: a Haiku worker's product (pilot run, single arm, rep1); fails hidden checks: max_length_hyphen.
import unicodedata
import re


def slugify(text: str, max_length: int | None = None) -> str:
    if max_length is not None and max_length < 1:
        raise ValueError("max_length must be at least 1")

    # Normalize unicode (NFKD decomposes accented chars into base + combining marks)
    # Then keep only ASCII characters (combining marks are > 127)
    text = unicodedata.normalize('NFKD', text)
    text = ''.join(c for c in text if ord(c) < 128)

    # Lowercase
    text = text.lower()

    # Replace runs of non-alphanumeric characters with single hyphen
    text = re.sub(r'[^a-z0-9]+', '-', text)

    # Strip leading and trailing hyphens
    text = text.strip('-')

    # Handle max_length truncation
    if max_length is not None and len(text) > max_length:
        truncated = text[:max_length]
        last_hyphen_idx = truncated.rfind('-')

        if last_hyphen_idx > 0:
            # Found a hyphen within max_length, cut at that hyphen
            text = truncated[:last_hyphen_idx]
        else:
            # No hyphen found or first word is longer than max_length, cut to max_length
            text = text[:max_length]

    return text
