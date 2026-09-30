# Harvested: a Haiku worker's product (pilot run, firm arm, rep1); fails hidden checks: parse_decimals, parse_invalid, parse_negative, parse_order, parse_valid, roundtrip.
import re

# Unit definitions in descending order
UNITS = [
    ('w', 604800),
    ('d', 86400),
    ('h', 3600),
    ('m', 60),
    ('s', 1),
    ('ms', 0.001),
]

UNIT_ORDER = {unit: i for i, (unit, _) in enumerate(UNITS)}


def parse_duration(text):
    """Convert duration string to seconds."""
    if not isinstance(text, str):
        raise ValueError("Input must be a string")

    original_text = text
    text = text.strip()

    if not text:
        raise ValueError("Empty duration string")

    # Check for leading minus sign
    is_negative = False
    if text.startswith('-'):
        is_negative = True
        text = text[1:].lstrip()

    if not text:
        raise ValueError("No duration value after minus sign")

    # Parse components
    total = 0.0
    last_unit_order = -1

    # Split by whitespace and process
    remaining = text

    while remaining:
        remaining = remaining.lstrip()
        if not remaining:
            break

        # Match number followed by unit (ms must come before m)
        match = re.match(r'^([0-9]+(?:\.[0-9]+)?)(w|d|h|ms|m|s)', remaining)

        if not match:
            raise ValueError(f"Invalid duration format: {original_text}")

        number_str = match.group(1)
        unit = match.group(2)

        # Validate number format
        if number_str.startswith('.') or number_str.endswith('.'):
            raise ValueError(f"Invalid number format: {original_text}")

        # Check for invalid patterns like scientific notation or underscores
        if 'e' in number_str.lower() or '_' in number_str:
            raise ValueError(f"Invalid number format: {original_text}")

        # Check unit validity and order
        if unit not in UNIT_ORDER:
            raise ValueError(f"Unknown unit: {unit}")

        current_unit_order = UNIT_ORDER[unit]
        if current_unit_order >= last_unit_order:
            raise ValueError(f"Units not in strictly descending order: {original_text}")
        last_unit_order = current_unit_order

        # Convert to seconds
        number = float(number_str)
        unit_seconds = next(s for u, s in UNITS if u == unit)
        total += number * unit_seconds

        # Move to next component
        remaining = remaining[match.end():]

    if is_negative:
        total = -total

    return total


def format_duration(seconds):
    """Convert seconds to duration string."""
    if not isinstance(seconds, (int, float)):
        raise ValueError("Input must be a number")

    # Round to nearest millisecond using round-half-away-from-zero
    milliseconds = int(seconds * 1000 + (0.5 if seconds >= 0 else -0.5))

    # Handle zero case
    if milliseconds == 0:
        return "0s"

    # Handle negative
    is_negative = milliseconds < 0
    remaining_ms = abs(milliseconds)

    # Build components using millisecond precision throughout
    components = []

    unit_ms_values = [
        ('w', 604800000),
        ('d', 86400000),
        ('h', 3600000),
        ('m', 60000),
        ('s', 1000),
        ('ms', 1),
    ]

    for unit, unit_ms in unit_ms_values:
        if remaining_ms == 0:
            break

        count = remaining_ms // unit_ms
        if count > 0:
            components.append(f"{count}{unit}")
            remaining_ms -= count * unit_ms

    result = "".join(components)

    if is_negative:
        result = "-" + result

    return result
