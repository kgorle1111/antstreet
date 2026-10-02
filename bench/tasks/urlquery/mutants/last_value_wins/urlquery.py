# A repeated key keeps only its last value instead of collecting every value in a list.
_HEX = "0123456789abcdefABCDEF"
_SAFE = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~")


def _decode(part: str) -> str:
    raw = bytearray()
    i = 0
    while i < len(part):
        ch = part[i]
        if ch == "%":
            digits = part[i + 1 : i + 3]
            if len(digits) != 2 or any(d not in _HEX for d in digits):
                raise ValueError(f"bad percent escape in {part!r}")
            raw.append(int(digits, 16))
            i += 3
        else:
            raw += b" " if ch == "+" else ch.encode("utf-8")
            i += 1
    return raw.decode("utf-8")


def parse_query(qs: str) -> dict[str, list[str]]:
    if not isinstance(qs, str):
        raise ValueError("query string must be a str")
    if qs.startswith("?"):
        qs = qs[1:]
    result: dict[str, list[str]] = {}
    for segment in qs.split("&"):
        key, _, value = segment.partition("=")
        if key:
            result[_decode(key)] = [_decode(value)]
    return result


def _encode(text: str) -> str:
    out = []
    for byte in text.encode("utf-8"):
        if chr(byte) in _SAFE:
            out.append(chr(byte))
        elif byte == 0x20:
            out.append("+")
        else:
            out.append(f"%{byte:02X}")
    return "".join(out)


def build_query(params: dict) -> str:
    if not isinstance(params, dict):
        raise ValueError("params must be a dict")
    pairs = []
    for key, values in params.items():
        if not isinstance(key, str) or not key:
            raise ValueError("keys must be non-empty strings")
        if isinstance(values, str):
            values = [values]
        elif not isinstance(values, list | tuple):
            raise ValueError("values must be a str, list or tuple")
        for value in values:
            if not isinstance(value, str):
                raise ValueError("every value must be a str")
            pairs.append(f"{_encode(key)}={_encode(value)}")
    return "&".join(pairs)
