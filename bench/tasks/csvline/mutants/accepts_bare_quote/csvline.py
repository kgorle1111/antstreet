# A double quote inside an unquoted field is accepted instead of raising ValueError.
def parse_line(line: str) -> list[str]:
    fields: list[str] = []
    n = len(line)
    i = 0
    while True:
        if line.startswith('"', i):
            i += 1
            parts = []
            while True:
                end = line.find('"', i)
                if end == -1:
                    raise ValueError("unterminated quoted field")
                parts.append(line[i:end])
                if line.startswith('"', end + 1):
                    parts.append('"')
                    i = end + 2
                else:
                    i = end + 1
                    break
            fields.append("".join(parts))
            if i < n and line[i] != ",":
                raise ValueError("text after a closing quote")
        else:
            end = line.find(",", i)
            if end == -1:
                end = n
            raw = line[i:end]
            if any(ch in raw for ch in '\r\n'):
                raise ValueError("bare quote or line break in an unquoted field")
            fields.append(raw)
            i = end
        if i >= n:
            return fields
        i += 1  # the comma


def _needs_quotes(field: str) -> bool:
    if any(ch in field for ch in ',"\r\n'):
        return True
    return bool(field) and (field[0].isspace() or field[-1].isspace())


def format_line(fields: list[str]) -> str:
    if not fields:
        raise ValueError("a record needs at least one field")
    if not all(isinstance(f, str) for f in fields):
        raise ValueError("fields must be strings")
    return ",".join('"' + f.replace('"', '""') + '"' if _needs_quotes(f) else f for f in fields)
