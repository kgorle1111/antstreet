# A None value is compared like any other value, so only an absent key counts as missing.
def sort_records(records: list[dict], keys: list[str]) -> list[dict]:
    if not isinstance(records, list | tuple) or not isinstance(keys, list | tuple):
        raise TypeError("records and keys must be lists")
    parsed = []
    for spec in keys:
        if not isinstance(spec, str):
            raise TypeError(f"key spec must be a str, got {type(spec).__name__}")
        descending = spec.startswith("-")
        field = spec[1:] if descending else spec
        if not field:
            raise ValueError(f"key spec has no field name: {spec!r}")
        parsed.append((field, descending))
    if not all(isinstance(r, dict) for r in records):
        raise TypeError("every record must be a dict")
    result = list(records)
    for field, descending in reversed(parsed):
        present = [r for r in result if field in r]
        missing = [r for r in result if field not in r]
        # reverse=True keeps equal elements in their original order, so descending stays stable.
        result = sorted(present, key=lambda r, f=field: r[f], reverse=descending) + missing
    return result
