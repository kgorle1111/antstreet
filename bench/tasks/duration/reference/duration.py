import re

_UNITS = (("w", 604800.0), ("d", 86400.0), ("h", 3600.0), ("m", 60.0), ("s", 1.0), ("ms", 0.001))
_MS_PER_UNIT = (604_800_000, 86_400_000, 3_600_000, 60_000, 1_000, 1)
_SECONDS = dict(_UNITS)
_RANK = {name: i for i, (name, _) in enumerate(_UNITS)}
_COMPONENT = re.compile(r"([0-9]+(?:\.[0-9]+)?)([A-Za-z]+)\s*")


def parse_duration(text: str) -> float:
    if not isinstance(text, str):
        raise ValueError(f"expected str, got {type(text).__name__}")
    body = text.strip()
    negative = body.startswith("-")
    if negative:
        body = body[1:]
    if not body:
        raise ValueError("empty duration")
    total = 0.0
    last_rank = -1
    pos = 0
    while pos < len(body):
        match = _COMPONENT.match(body, pos)
        if match is None:
            raise ValueError(f"bad duration component at position {pos}")
        number, unit = match.groups()
        if unit not in _SECONDS:
            raise ValueError(f"unknown unit {unit!r}")
        if _RANK[unit] <= last_rank:
            raise ValueError(f"unit {unit!r} repeated or out of order")
        last_rank = _RANK[unit]
        total += float(number) * _SECONDS[unit]
        pos = match.end()
    return -total if negative else total


def format_duration(seconds: float) -> str:
    millis = round(abs(seconds) * 1000)
    if millis == 0:
        return "0s"
    parts = []
    for (name, _), size in zip(_UNITS, _MS_PER_UNIT, strict=True):
        count, millis = divmod(millis, size)
        if count:
            parts.append(f"{count}{name}")
    return ("-" if seconds < 0 else "") + "".join(parts)
