Create a Python module `cidr4.py` (standard library only) for IPv4 addresses and CIDR blocks. Do not import `ipaddress` or `socket`; the module is judged on behaviour only, but the point is to write the arithmetic yourself. It provides these functions:

    parse_ip(text: str) -> int
    parse_cidr(text: str, strict: bool = True) -> tuple[int, int]
    format_cidr(address: int, prefix: int) -> str
    contains(cidr: str, ip: str) -> bool
    overlaps(a: str, b: str) -> bool
    summarise(cidrs: list[str] | tuple[str, ...]) -> list[str]
    usable_hosts(cidr: str) -> int

In this text, examples of input are written as Python string literals. An address is held as an int from 0 to 4294967295 (`'0.0.0.0'` is 0, `'255.255.255.255'` is 4294967295, `'10.0.0.1'` is 167772161).

1. `parse_ip(text)` reads a dotted quad: exactly four parts separated by `.`, each part a decimal number from 0 to 255 written with ASCII digits only. A part has no sign, no spaces and no leading zeros (`'0'` is fine; `'01'`, `'00'` and `'007'` are not). Anything else raises `ValueError`: `''`, `'1.2.3'`, `'1.2.3.4.5'`, `'1.2.3.'`, `'1..3.4'`, `'256.1.1.1'`, `' 1.2.3.4'`, `'1.2.3.4 '`, `'1.2.3.x'`, `'0x1.2.3.4'`, `'-1.2.3.4'`, and a part with a digit of another script such as `'1.2.3.٤'`.
2. `parse_cidr(text)` reads `address/prefix` and returns `(address, prefix)` with the address as an int and the prefix as an int. The address follows rule 1. The prefix is a whole decimal number from 0 to 32 written with ASCII digits only and no leading zeros (`'0'` is fine; `'08'` is not), after exactly one `/`. A text with no `/`, an empty address or prefix, a second `/`, a prefix above 32, or anything else that is wrong raises `ValueError`.
3. The host bits of a block are the address bits that the prefix leaves free (the low `32 - prefix` bits). With `strict=True` (the default), a block with any host bit set is an error: `'10.0.0.1/24'` raises `ValueError`, while `'10.0.0.0/24'`, `'10.0.0.1/32'` and `'0.0.0.0/0'` are fine. With `strict=False` the host bits are cleared instead: `parse_cidr('10.0.0.77/24', strict=False)` is `(167772160, 24)`. All the functions below that take a CIDR text use the strict reading.
4. `format_cidr(address, prefix)` is the reverse: it returns the text `'10.0.0.0/24'`. It raises `ValueError` when the address is outside 0 to 4294967295, the prefix is outside 0 to 32, or the address has host bits set for that prefix. It raises `TypeError` when either argument is not an `int`.
5. `contains(cidr, ip)` is `True` when the address `ip` (rule 1) lies in the block, counting its first and last address: `contains('10.0.0.0/24', '10.0.0.255')` is `True`, `'10.0.1.0'` is `False`; a `/32` contains only its own address and `'0.0.0.0/0'` contains every address.
6. `overlaps(a, b)` is `True` when the two blocks share at least one address. Two blocks either nest or are separate, and blocks that only touch (`'10.0.0.0/25'` and `'10.0.0.128/25'`) do not overlap. The result does not depend on the order of the arguments.
7. `summarise(cidrs)` takes a list or tuple of CIDR texts and returns the smallest list of CIDR texts that covers exactly the same addresses, ordered by address. Blocks inside other blocks and repeated blocks disappear, and two blocks merge into their parent block when they are the two halves of it, repeatedly: `['10.0.0.0/25', '10.0.0.128/25']` gives `['10.0.0.0/24']`, `['10.0.0.0/24', '10.0.1.0/24', '10.0.2.0/23']` gives `['10.0.0.0/22']`. Neighbouring blocks that do not make up a block of the next size stay apart: `['10.0.1.0/24', '10.0.2.0/24']` gives `['10.0.1.0/24', '10.0.2.0/24']`. An empty list gives `[]`. An invalid item raises `ValueError`; a `cidrs` that is not a list or tuple raises `TypeError`.
8. `usable_hosts(cidr)` is the number of addresses a host can use: the block's size minus 2 (the network and the broadcast address), except that a `/31` has 2 and a `/32` has 1. `'10.0.0.0/24'` gives 254, `'10.0.0.0/30'` gives 2, `'10.0.0.0/31'` gives 2, `'10.0.0.1/32'` gives 1 and `'0.0.0.0/0'` gives 4294967294.
9. A text argument that is not a `str` raises `TypeError` in every function that takes one.
