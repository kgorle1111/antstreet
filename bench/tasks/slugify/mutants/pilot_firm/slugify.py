# Harvested: a Haiku worker's product (pilot run, firm arm, rep1); fails hidden checks: max_length_hyphen.
import unicodedata
import re


def slugify(text: str, max_length: int | None = None) -> str:
    if max_length is not None and max_length < 1:
        raise ValueError("max_length must be at least 1")

    # Decompose accented characters and remove combining marks
    nfd = unicodedata.normalize('NFD', text)
    cleaned = ''.join(c for c in nfd if unicodedata.category(c) != 'Mn')

    # Drop non-ASCII characters
    ascii_only = cleaned.encode('ascii', errors='ignore').decode('ascii')

    # Lowercase and replace runs of non-alphanumeric characters with hyphens
    slug = ascii_only.lower()
    slug = re.sub(r'[^a-z0-9]+', '-', slug)

    # Strip leading/trailing hyphens
    slug = slug.strip('-')

    # Handle max_length
    if max_length is not None and len(slug) > max_length:
        truncated = slug[:max_length]
        if truncated.endswith('-'):
            # Try to find the last hyphen before the end
            last_hyphen_idx = truncated[:-1].rfind('-')
            if last_hyphen_idx > 0:
                return truncated[:last_hyphen_idx]
            else:
                return truncated[:-1]
        else:
            return truncated

    return slug
