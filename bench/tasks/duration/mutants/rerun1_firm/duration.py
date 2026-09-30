# Harvested: a Haiku worker's product (rerun1 run, firm arm, rep1); fails hidden checks: parse_decimals.
def parse_duration(text: str) -> float:
    if not isinstance(text, str):
        raise ValueError("Input must be a string")

    text = text.strip()

    if not text:
        raise ValueError("Empty string")

    negative = False
    if text[0] == '-':
        negative = True
        text = text[1:]
        if not text or text[0] in ' \t\n\r':
            raise ValueError("No number after minus sign")

    if text and text[0] == '-':
        raise ValueError("Multiple signs")

    units = {
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
    found_component = False

    while i < len(text):
        while i < len(text) and text[i] in ' \t\n\r':
            i += 1

        if i >= len(text):
            break

        if not text[i].isdigit():
            raise ValueError("Expected digit")

        num_start = i
        while i < len(text) and text[i].isdigit():
            i += 1

        if i < len(text) and text[i] == '.':
            i += 1
            if i >= len(text) or not text[i].isdigit():
                raise ValueError("Invalid decimal format")
            while i < len(text) and text[i].isdigit():
                i += 1

        num_str = text[num_start:i]
        number = float(num_str)

        if i < len(text) and text[i] == ' ':
            raise ValueError("Space between number and unit")

        if i >= len(text):
            raise ValueError("Number without unit")

        if i + 1 < len(text) and text[i:i+2] == 'ms':
            unit = 'ms'
            i += 2
        elif text[i] in 'wdhms':
            unit = text[i]
            i += 1
        else:
            raise ValueError("Invalid unit")

        if unit not in units:
            raise ValueError("Invalid unit")

        unit_index = unit_order.index(unit)
        if unit_index <= last_unit_index:
            raise ValueError("Units out of order or repeated")
        last_unit_index = unit_index

        total += number * units[unit]
        found_component = True

    if not found_component:
        raise ValueError("No components found")

    if negative:
        total = -total

    return total


def format_duration(seconds: float) -> str:
    ms_value = round(abs(seconds) * 1000)

    if ms_value == 0:
        return "0s"

    components = []

    weeks = ms_value // (7 * 24 * 3600 * 1000)
    ms_value %= (7 * 24 * 3600 * 1000)
    if weeks > 0:
        components.append(f"{weeks}w")

    days = ms_value // (24 * 3600 * 1000)
    ms_value %= (24 * 3600 * 1000)
    if days > 0:
        components.append(f"{days}d")

    hours = ms_value // (3600 * 1000)
    ms_value %= (3600 * 1000)
    if hours > 0:
        components.append(f"{hours}h")

    minutes = ms_value // (60 * 1000)
    ms_value %= (60 * 1000)
    if minutes > 0:
        components.append(f"{minutes}m")

    secs = ms_value // 1000
    ms_value %= 1000
    if secs > 0:
        components.append(f"{secs}s")

    if ms_value > 0:
        components.append(f"{ms_value}ms")

    result = "".join(components)

    if seconds < 0:
        result = "-" + result

    return result
