# replay treats text after the last newline as a record instead of ignoring the torn write.
import json
import os
import tempfile

_OPS = ("set", "delete")


def _check(op, key, value):
    if op not in _OPS:
        raise ValueError(f"unknown op {op!r}")
    if not isinstance(key, str) or not key:
        raise ValueError("key must be a non-empty str")
    if op == "delete":
        return (op, key, None)
    if not isinstance(value, str):
        raise ValueError("value of a set must be a str")
    return (op, key, value)


def _line(record):
    op, key, value = record
    return json.dumps({"op": op, "key": key, "value": value}) + "\n"


def _parse(raw, number):
    try:
        obj = json.loads(raw.decode("utf-8"))
    except ValueError as exc:
        raise ValueError(f"line {number}: not valid JSON") from exc
    if not isinstance(obj, dict) or set(obj) != {"op", "key", "value"}:
        raise ValueError(f"line {number}: not a record")
    if obj["op"] == "delete" and obj["value"] is not None:
        raise ValueError(f"line {number}: a delete has no value")
    try:
        return _check(obj["op"], obj["key"], obj["value"])
    except ValueError as exc:
        raise ValueError(f"line {number}: {exc}") from exc


class WriteAheadLog:
    def __init__(self, path):
        self.path = os.fspath(path)

    def append(self, op, key, value=None):
        line = _line(_check(op, key, value))
        with open(self.path, "a", encoding="utf-8", newline="") as f:
            f.write(line)
            f.flush()
            os.fsync(f.fileno())

    def replay(self):
        try:
            with open(self.path, "rb") as f:
                data = f.read()
        except FileNotFoundError:
            return []
        lines = data.split(b"\n")
        if lines[-1] == b"":
            lines.pop()
        return [_parse(raw, n) for n, raw in enumerate(lines, 1)]

    def rewrite(self, records):
        text = "".join(_line(_check(*r)) for r in records)
        directory = os.path.dirname(os.path.abspath(self.path))
        fd, tmp = tempfile.mkstemp(dir=directory, prefix=".wal-")
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
                f.write(text)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self.path)
        except BaseException:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise
