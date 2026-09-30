# Accented letters are dropped instead of becoming their plain letter (cafe becomes caf).
import re
import unicodedata


def slugify(text: str, max_length: int | None = None) -> str:
    if max_length is not None and max_length < 1:
        raise ValueError("max_length must be at least 1")
    ascii_text = text.encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")
    if max_length is None or len(slug) <= max_length:
        return slug
    last_hyphen = slug[: max_length + 1].rfind("-")
    return slug[:last_hyphen] if last_hyphen > 0 else slug[:max_length]
