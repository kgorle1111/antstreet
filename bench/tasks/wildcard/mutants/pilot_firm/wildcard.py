# Harvested: a Haiku worker's product (pilot run, firm arm, rep1); fails hidden checks: escapes, polynomial_time.
from typing import Iterable


def parse_charset(pattern: str, start: int) -> tuple[bool, set, int]:
    """Parse a character set starting at pattern[start].
    Returns (is_negated, char_set, end_index).
    Raises ValueError if the character set is invalid.
    """
    if pattern[start] != '[':
        raise ValueError("Expected [")

    i = start + 1
    is_negated = False

    if i < len(pattern) and pattern[i] == '!':
        is_negated = True
        i += 1

    elements = []

    # ] immediately after [ or [! is literal
    if i < len(pattern) and pattern[i] == ']':
        elements.append(']')
        i += 1

    has_content = len(elements) > 0

    while i < len(pattern):
        if pattern[i] == '\\':
            if i + 1 >= len(pattern):
                raise ValueError("Lone backslash in character set")
            # Mark escaped characters as tuples so they can't form ranges
            elements.append(('escaped', pattern[i + 1]))
            has_content = True
            i += 2
        elif pattern[i] == ']':
            if not has_content:
                raise ValueError("Empty character set")
            # Convert elements to character set, handling ranges
            chars = set()
            j = 0
            while j < len(elements):
                # Check if this forms a range: elements[j] - elements[j+2]
                # Both elements must be regular (not escaped) characters
                if (j + 2 < len(elements) and
                    elements[j + 1] == '-' and
                    not isinstance(elements[j], tuple) and
                    not isinstance(elements[j + 2], tuple)):
                    # This is a range
                    start_char = elements[j]
                    end_char = elements[j + 2]
                    for ch in range(ord(start_char), ord(end_char) + 1):
                        chars.add(chr(ch))
                    j += 3
                else:
                    # Regular character or escaped character
                    if isinstance(elements[j], tuple):
                        chars.add(elements[j][1])
                    else:
                        chars.add(elements[j])
                    j += 1
            return (is_negated, chars, i + 1)
        else:
            elements.append(pattern[i])
            has_content = True
            i += 1

    raise ValueError("Unclosed character set")


def validate_pattern(pattern: str) -> None:
    """Validate pattern syntax."""
    i = 0
    while i < len(pattern):
        if pattern[i] == '\\':
            if i + 1 >= len(pattern):
                raise ValueError("Lone backslash at end of pattern")
            i += 2
        elif pattern[i] == '[':
            # Validate character set by parsing it
            _, _, i = parse_charset(pattern, i)
        else:
            i += 1


def match(pattern: str, text: str) -> bool:
    """Match text against pattern using glob-like wildcards.

    Pattern syntax:
    - Ordinary characters match themselves
    - * matches any run (including none)
    - ? matches exactly one character
    - [...] is a set matching one character from the set
    - [!...] is a negated set
    - ] directly after [ or [! is literal
    - - is range operator only between members or literal at start/end
    - backslash escapes next character
    - Case-sensitive, matches whole string only
    """
    validate_pattern(pattern)

    memo = {}

    def dp(p_idx, t_idx):
        if (p_idx, t_idx) in memo:
            return memo[(p_idx, t_idx)]

        # Base case: reached end of pattern
        if p_idx == len(pattern):
            result = t_idx == len(text)
        elif pattern[p_idx] == '*':
            # Try matching 0, 1, 2, ... characters from text
            result = False
            for match_len in range(len(text) - t_idx + 1):
                if dp(p_idx + 1, t_idx + match_len):
                    result = True
                    break
        elif pattern[p_idx] == '\\':
            # Escaped character - must match the next character literally
            if p_idx + 1 < len(pattern) and t_idx < len(text) and pattern[p_idx + 1] == text[t_idx]:
                result = dp(p_idx + 2, t_idx + 1)
            else:
                result = False
        elif pattern[p_idx] == '[':
            # Character set
            is_negated, chars, next_idx = parse_charset(pattern, p_idx)
            if t_idx < len(text):
                char_matches = text[t_idx] in chars
                if is_negated:
                    char_matches = not char_matches
                if char_matches:
                    result = dp(next_idx, t_idx + 1)
                else:
                    result = False
            else:
                result = False
        elif pattern[p_idx] == '?':
            # Match exactly one character
            if t_idx < len(text):
                result = dp(p_idx + 1, t_idx + 1)
            else:
                result = False
        else:
            # Regular character - must match exactly
            if t_idx < len(text) and pattern[p_idx] == text[t_idx]:
                result = dp(p_idx + 1, t_idx + 1)
            else:
                result = False

        memo[(p_idx, t_idx)] = result
        return result

    return dp(0, 0)


def filter_names(pattern: str, names: Iterable[str]) -> list[str]:
    """Filter names matching pattern, preserving order and duplicates."""
    validate_pattern(pattern)
    return [name for name in names if match(pattern, name)]
