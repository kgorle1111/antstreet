# usable_hosts always subtracts 2, so a /31 gives 0 and a /32 gives -1.
"""IPv4 addresses and CIDR blocks as plain ints; strict parsing, exact summarisation."""

_MAX = 2**32 - 1


def _need_str(value: object) -> None:
    if not isinstance(value, str):
        raise TypeError(f"expected str, got {type(value).__name__}")


def _decimal(part: str, limit: int) -> bool:
    return (
        part.isascii()
        and part.isdigit()
        and (part == "0" or not part.startswith("0"))
        and int(part) <= limit
    )


def parse_ip(text: str) -> int:
    _need_str(text)
    parts = text.split(".")
    if len(parts) != 4 or not all(_decimal(p, 255) for p in parts):
        raise ValueError(f"not a dotted quad: {text!r}")
    value = 0
    for part in parts:
        value = (value << 8) | int(part)
    return value


def parse_cidr(text: str, strict: bool = True) -> tuple[int, int]:
    _need_str(text)
    ip, slash, prefix_text = text.partition("/")
    if not slash or not _decimal(prefix_text, 32):
        raise ValueError(f"not address/prefix: {text!r}")
    address = parse_ip(ip)
    prefix = int(prefix_text)
    host_mask = _MAX >> prefix
    if address & host_mask:
        if strict:
            raise ValueError(f"host bits set in {text!r}")
        address &= ~host_mask
    return address, prefix


def format_cidr(address: int, prefix: int) -> str:
    for value in (address, prefix):
        if not isinstance(value, int):
            raise TypeError(f"expected int, got {type(value).__name__}")
    if not 0 <= address <= _MAX or not 0 <= prefix <= 32 or address & (_MAX >> prefix):
        raise ValueError(f"not a CIDR block: {address}/{prefix}")
    octets = (address >> shift & 255 for shift in (24, 16, 8, 0))
    return ".".join(map(str, octets)) + f"/{prefix}"


def _span(cidr: str) -> tuple[int, int]:
    address, prefix = parse_cidr(cidr)
    return address, address | (_MAX >> prefix)


def contains(cidr: str, ip: str) -> bool:
    start, end = _span(cidr)
    return start <= parse_ip(ip) <= end


def overlaps(a: str, b: str) -> bool:
    (a_start, a_end), (b_start, b_end) = _span(a), _span(b)
    return a_start <= b_end and b_start <= a_end


def summarise(cidrs: list[str] | tuple[str, ...]) -> list[str]:
    if not isinstance(cidrs, list | tuple):
        raise TypeError(f"expected list or tuple, got {type(cidrs).__name__}")
    merged: list[list[int]] = []
    for start, end in sorted(_span(c) for c in cidrs):
        if merged and start <= merged[-1][1] + 1:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    out: list[str] = []
    for start, end in merged:
        while start <= end:
            size = start & -start if start else 1 << 32  # largest aligned block at start
            while start + size - 1 > end:
                size >>= 1
            out.append(format_cidr(start, 33 - size.bit_length()))
            start += size
    return out


def usable_hosts(cidr: str) -> int:
    _, prefix = parse_cidr(cidr)
    size = 1 << (32 - prefix)
    return size - 2
