# Harvested: a Haiku worker's product (pilot run, single arm, rep1); fails hidden checks: parse_negative.
def parse_duration(text: str) -> float:
    """Parse a duration string into seconds."""
    if not isinstance(text, str):
        raise ValueError("Input must be a string")

    # Strip leading/trailing whitespace
    text = text.strip()

    # Check for empty string
    if not text:
        raise ValueError("Duration string cannot be empty")

    # Check for leading minus sign
    negative = False
    if text.startswith('-'):
        negative = True
        text = text[1:]
        # No whitespace allowed between minus and first number
        if text and text[0] in ' \t\n\r':
            raise ValueError("Whitespace not allowed after minus sign")

    # Check for another minus sign
    if '-' in text:
        raise ValueError("Invalid minus sign")

    # Units and their conversions to seconds
    unit_values = {
        'w': 7 * 24 * 3600,
        'd': 24 * 3600,
        'h': 3600,
        'm': 60,
        's': 1,
        'ms': 0.001
    }

    unit_order = ['w', 'd', 'h', 'm', 's', 'ms']
    last_unit_index = -1

    total = 0.0
    i = 0

    def is_ascii_digit(c):
        return '0' <= c <= '9'

    while i < len(text):
        # Skip whitespace
        while i < len(text) and text[i] in ' \t\n\r':
            i += 1

        if i >= len(text):
            break

        # Parse number
        start = i
        while i < len(text) and is_ascii_digit(text[i]):
            i += 1

        if i == start:
            raise ValueError("Expected a number")

        # Check for decimal point
        if i < len(text) and text[i] == '.':
            i += 1
            if i >= len(text) or not is_ascii_digit(text[i]):
                raise ValueError("Invalid decimal number")
            while i < len(text) and is_ascii_digit(text[i]):
                i += 1

        number_str = text[start:i]
        number = float(number_str)

        # Check for unit
        if i >= len(text) or text[i] in ' \t\n\r':
            raise ValueError("Number without unit")

        # Determine unit
        if text[i:i+2] == 'ms':
            unit = 'ms'
            i += 2
        elif text[i:i+1] in unit_values:
            unit = text[i:i+1]
            i += 1
        else:
            raise ValueError("Unknown unit")

        # Check unit order
        unit_index = unit_order.index(unit)
        if unit_index <= last_unit_index:
            raise ValueError("Units out of order or repeated")
        last_unit_index = unit_index

        # Add to total
        total += number * unit_values[unit]

    if negative:
        total = -total

    return total


def format_duration(seconds: float) -> str:
    """Format seconds into a duration string."""
    if not isinstance(seconds, (int, float)):
        raise ValueError("Input must be a number")

    # Handle the special case of 0
    if seconds == 0:
        return "0s"

    # Check if negative
    negative = seconds < 0
    seconds = abs(seconds)

    # Round to nearest millisecond
    total_ms = round(seconds * 1000)

    # Handle the case where rounding resulted in 0
    if total_ms == 0:
        return "0s"

    # Define units in milliseconds
    units = [
        ('w', 7 * 24 * 3600 * 1000),
        ('d', 24 * 3600 * 1000),
        ('h', 3600 * 1000),
        ('m', 60 * 1000),
        ('s', 1000),
        ('ms', 1)
    ]

    components = []
    for unit_name, unit_ms in units:
        if total_ms >= unit_ms:
            count = total_ms // unit_ms
            total_ms = total_ms % unit_ms
            components.append(f"{count}{unit_name}")

    result = "".join(components)

    if negative:
        result = "-" + result

    return result
