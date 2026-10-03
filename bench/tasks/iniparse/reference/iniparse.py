def parse_ini(text: str) -> dict[str, dict[str, str]]:
    if not isinstance(text, str):
        raise ValueError("text must be a str")
    result: dict[str, dict[str, str]] = {}
    current: dict[str, str] | None = None  # section "" exists only once a header-less key is read
    for number, raw in enumerate(text.split("\n"), 1):
        line = raw.strip()
        if not line or line[0] in ";#":
            continue
        if line[0] == "[":
            if not line.endswith("]"):
                raise ValueError(f"line {number}: section header must end with ]")
            name = line[1:-1].strip()
            if not name:
                raise ValueError(f"line {number}: empty section name")
            current = result.setdefault(name, {})
            continue
        key, sep, value = line.partition("=")
        key = key.strip()
        if not sep or not key:
            raise ValueError(f"line {number}: expected key = value")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] == '"':
            value = value[1:-1]
        if current is None:
            current = result.setdefault("", {})
        current[key] = value
    return result
