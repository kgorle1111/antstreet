"""The automatic plant kinds and their oracles (PR 2 of ops/c4-approval-study-2026-10-16/DESIGN.md).

A kind rewrites the text of ONE check file. It parses the file with `ast`, picks the node to change
from the rng, unparses only the replacement and splices it in at the node's byte offsets, so every
other byte (comments, quote style, blank lines) is the draft's own: a planted file must not look
re-formatted next to its unplanted neighbours. A check is never imported or run here. An oracle
runs it only through the sandboxed gate (`antstreet.gate.run_gate`), directly or through the code
that already wraps it: `bench/score.py` (`count_wrong_checks`, `score_draft`) and
`termsheet.empty_checks_problems`, the empty-workspace validation approval runs (T08).

  wrong_value      one `assert <expr> == <literal>` gets a nearby literal (int/float +-1, one
                   letter or digit of a str changed). Oracle: the reference solution passes the
                   original and fails the planted check.
  vacuous          each test function keeps its imports and asserts only that the imported names
                   exist (`is not None`). Oracle: passes on the reference solution, still fails on
                   an empty workspace (so T08 does not catch it), and passes on a stub product
                   defining those names with no logic, which the original fails.
  under_specified  one assert (or one of several test functions) is dropped. Oracle: the reference
                   still passes, and some mutant the original killed survives the planted check.
"""

from __future__ import annotations

import ast
import functools
import random
import string
import sys
import tempfile
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TypeGuard

from antstreet.bench.score import count_wrong_checks, score_draft
from antstreet.bench.tasks import MUTANT_TIMEOUT_S, BenchTask
from antstreet.gate import Check, run_gate
from antstreet.termsheet import empty_checks_problems

# Not the product: a vacuous check asserts nothing about these, and the stub never shadows them.
_NOT_PRODUCT = frozenset(sys.stdlib_module_names) | {"pytest", "_pytest", "hypothesis"}
_BOM = b"\xef\xbb\xbf"


class Inapplicable(Exception):
    """This kind has nothing to change in this check; the message says why."""


@dataclass(frozen=True, slots=True)
class OracleResult:
    holds: bool
    detail: str  # what the gate showed, in words, for the key


def check_id_of(file: str) -> str:
    """The id `bench/score.py` (`draft_checks`) gives a check file: test_c01.py is c01."""
    return file.removesuffix(".py").removeprefix("test_")


# --- text surgery -----------------------------------------------------------------------------


def _parse(original: bytes) -> ast.Module:
    # kn: BOM and CR line endings break the byte-offset splice; refused, not handled (no archived
    # draft has either). Handle them if a real draft is refused for it.
    if original.startswith(_BOM) or b"\r" in original:
        raise Inapplicable("the check has a BOM or CR line endings, which this kind does not edit")
    try:
        return ast.parse(original.decode("utf-8"))
    except (UnicodeDecodeError, SyntaxError) as exc:
        raise Inapplicable(f"the check does not parse: {exc}") from exc


class _Text:
    """The check's bytes with `ast` (line, byte column) positions turned into byte offsets."""

    def __init__(self, data: bytes) -> None:
        self.data = data
        self.starts = [0] + [i + 1 for i, b in enumerate(data) if b == 0x0A]

    def at(self, line: int, col: int) -> int:
        return self.starts[line - 1] + col

    def start(self, node: ast.AST) -> int:
        return self.at(node.lineno, node.col_offset)  # type: ignore[attr-defined]

    def end(self, node: ast.AST) -> int:
        return self.at(node.end_lineno, node.end_col_offset)  # type: ignore[attr-defined]

    def segment(self, node: ast.AST) -> bytes:
        return self.data[self.start(node) : self.end(node)]

    def line_start(self, line: int) -> int:
        return self.starts[line - 1]

    def line_end(self, line: int) -> int:
        """The offset just past line `line`'s newline (or the end of the file)."""
        return self.starts[line] if line < len(self.starts) else len(self.data)

    def starts_before(self, offset: int) -> int:
        """The start of the line before the one starting at `offset`."""
        return self.starts[self.starts.index(offset) - 1]

    def splice(self, start: int, end: int, new: bytes) -> bytes:
        return self.data[:start] + new + self.data[end:]

    def owns_lines(self, node: ast.stmt) -> bool:
        """The statement alone on its lines: only indentation before it, nothing but a comment or
        whitespace after it, so removing whole lines removes exactly it."""
        before = self.data[self.line_start(node.lineno) : self.start(node)]
        after = self.data[self.end(node) : self.line_end(node.end_lineno or node.lineno)]
        return not before.strip() and (not after.strip() or after.strip().startswith(b"#"))


def _test_functions(tree: ast.Module) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    """The functions pytest collects as tests: module-level `test*`, and `test*` methods of
    module-level `Test*` classes."""
    found: list[ast.FunctionDef | ast.AsyncFunctionDef] = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
            found += [n for n in node.body if _is_test(n)]
        elif _is_test(node):
            found.append(node)
    return found


def _is_test(node: ast.stmt) -> TypeGuard[ast.FunctionDef | ast.AsyncFunctionDef]:
    return isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name.startswith("test")


def _statement_lists(node: ast.AST) -> Iterator[list[ast.stmt]]:
    """Every block of statements under `node`, nested ones included."""
    for child in ast.walk(node):
        for field in ("body", "orelse", "finalbody"):
            block = getattr(child, field, None)
            if isinstance(block, list) and block and isinstance(block[0], ast.stmt):
                yield block
        for handler in getattr(child, "handlers", []) or []:
            yield handler.body


# --- wrong_value ------------------------------------------------------------------------------


def _literal_sites(text: _Text, tree: ast.Module) -> list[ast.Constant]:
    """The right-hand literals of `assert <expr> == <literal>` in test functions, written plainly
    enough that the new value can be spelled the way the draft spelled the old one."""
    sites: list[ast.Constant] = []
    for fn in _test_functions(tree):
        for node in ast.walk(fn):
            if not (
                isinstance(node, ast.Assert)
                and isinstance(node.test, ast.Compare)
                and len(node.test.ops) == 1
                and isinstance(node.test.ops[0], ast.Eq)
                and isinstance(node.test.comparators[0], ast.Constant)
            ):
                continue
            literal = node.test.comparators[0]
            if _spelled_plainly(text.segment(literal), literal.value):
                sites.append(literal)
    return sites


def _spelled_plainly(segment: bytes, value: object) -> bool:
    if isinstance(value, bool) or value is None:
        return False
    if isinstance(value, int | float):
        return segment == repr(value).encode()
    if isinstance(value, str):
        if not any(c.isascii() and c.isalnum() for c in value):
            return False
        return any(segment == q + value.encode() + q for q in (b'"', b"'")) and not any(
            c in value for c in "\"'\\"
        )
    return False


def _perturb(value: object, rng: random.Random) -> object:
    if isinstance(value, int):
        return value + rng.choice((-1, 1))
    if isinstance(value, float):
        return value + rng.choice((-1.0, 1.0))
    assert isinstance(value, str)  # _spelled_plainly admits nothing else
    # A digit when there is one: "1.6 KiB" for "1.5 KiB" reads like a slip, "1.5 KiZ" like a typo.
    positions = [i for i, c in enumerate(value) if c.isascii() and c.isdigit()] or [
        i for i, c in enumerate(value) if c.isascii() and c.isalpha()
    ]
    i = rng.choice(positions)
    old = value[i]
    if old.isdigit():
        leading = (i == 0 or not value[i - 1].isdigit()) and value[i + 1 : i + 2].isdigit()
        pool = string.digits[1:] if leading else string.digits  # never "0023" for "1023"
    else:
        pool = string.ascii_lowercase if old.islower() else string.ascii_uppercase
    return value[:i] + rng.choice([c for c in pool if c != old]) + value[i + 1 :]


def _respell(segment: bytes, new: object) -> bytes:
    if isinstance(new, str):
        quote = segment[:1]
        return quote + new.encode() + quote
    return repr(new).encode()


class WrongValue:
    name = "wrong_value"

    def plant(self, original: bytes, rng: random.Random) -> bytes:
        tree = _parse(original)
        text = _Text(original)
        sites = _literal_sites(text, tree)
        if not sites:
            raise Inapplicable(
                "no `assert <expr> == <literal>` with a plainly written int, float or str literal"
            )
        site = rng.choice(sites)
        new = _respell(text.segment(site), _perturb(site.value, rng))
        return text.splice(text.start(site), text.end(site), new)

    def oracle(self, original: bytes, planted: bytes, file: str, task: BenchTask) -> OracleResult:
        if _wrong_on_reference(task, file, original):
            raise Inapplicable("the reference solution already fails the draft's check")
        after = _wrong_on_reference(task, file, planted)
        holds = after
        return OracleResult(
            holds,
            f"reference solution: original passes, planted {_verb(not after)}",
        )


# kn: oracle gate results cached per process by content; a flaky result sticks until exit
@functools.lru_cache(maxsize=256)
def _wrong_on_reference(task: BenchTask, file: str, data: bytes) -> bool:
    """Whether the reference solution fails this one check (bench/score.py `count_wrong_checks`).
    Cached: the draws of one check share the original's run."""
    with tempfile.TemporaryDirectory(prefix="boss_oracle_") as tmp:
        (Path(tmp) / file).write_bytes(data)
        return count_wrong_checks(task, Path(tmp)) == 1


# --- vacuous ----------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Imported:
    module: str  # the product module, one plain name
    name: str | None  # the imported name; None for `import module`
    bound: str  # the name the check uses


def _product_imports(stmts: Sequence[ast.stmt]) -> list[_Imported]:
    found: list[_Imported] = []
    for node in stmts:
        if isinstance(node, ast.ImportFrom):
            if node.level or not node.module or node.module.split(".")[0] in _NOT_PRODUCT:
                continue
            for alias in node.names:
                if alias.name == "*":
                    raise Inapplicable("the check uses `import *`, so its names are unknown")
                found.append(_Imported(node.module, alias.name, alias.asname or alias.name))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] not in _NOT_PRODUCT:
                    found.append(_Imported(alias.name, None, alias.asname or alias.name))
    for item in found:
        if not item.module.isidentifier():
            raise Inapplicable(f"the check imports the dotted module {item.module!r}; no stub")
    return found


def _existence(item: _Imported) -> str:
    # Not `callable(...)`: an imported constant (`UNITS = (...)`) exists but is not callable, and
    # the vacuous check must still pass on a correct product. The oracle checks that it does.
    return f"assert {item.bound} is not None"


class Vacuous:
    name = "vacuous"

    def plant(self, original: bytes, rng: random.Random) -> bytes:
        del rng  # one rewrite per check: nothing to choose
        tree = _parse(original)
        text = _Text(original)
        functions = _test_functions(tree)
        module_level = _product_imports(tree.body)
        edits: list[tuple[int, int, bytes]] = []
        for fn in functions:
            body = fn.body
            if ast.get_docstring(fn, clean=False) is not None:
                body = body[1:]
            if not body:
                continue
            imports = [s for s in body if isinstance(s, ast.Import | ast.ImportFrom)]
            names = _product_imports(imports) or module_level
            if not names:
                raise Inapplicable(f"{fn.name} uses nothing imported from the product")
            first = body[0]
            indent = text.data[text.line_start(first.lineno) : text.start(first)]
            if indent.strip():
                raise Inapplicable(f"{fn.name} starts its body on the `def` line")
            lines = [text.segment(s).decode() for s in imports]
            lines += [_existence(item) for item in dict.fromkeys(names)]
            new = ("\n" + indent.decode()).join(lines).encode()
            edits.append((text.start(first), text.end(body[-1]), new))
        if not edits:
            raise Inapplicable("the check has no test function with a body to replace")
        data = original
        for start, end, new in sorted(edits, reverse=True):  # back to front: offsets stay valid
            data = data[:start] + new + data[end:]
        return data

    def oracle(self, original: bytes, planted: bytes, file: str, task: BenchTask) -> OracleResult:
        check = Check(check_id_of(file), file)
        # A plant the reference fails is wrong, not vacuous: it must never be keyed vacuous.
        if _wrong_on_reference(task, file, planted):
            return OracleResult(False, "reference solution: planted fails")
        try:
            stub_files = _stub(planted)
        except Inapplicable as exc:
            return OracleResult(False, str(exc))
        with tempfile.TemporaryDirectory(prefix="boss_oracle_") as tmp:
            root = Path(tmp)
            for folder, data in (("orig", original), ("new", planted)):
                (root / folder).mkdir()
                (root / folder / file).write_bytes(data)
            (root / "stub").mkdir()
            for name, source in stub_files.items():
                (root / "stub" / name).write_text(source, encoding="utf-8")
            empty = empty_checks_problems([check], root / "new")  # approval's T08, same timeout
            on_stub = run_gate(root / "stub", root / "new", [check], timeout_s=MUTANT_TIMEOUT_S)
            orig_stub = run_gate(root / "stub", root / "orig", [check], timeout_s=MUTANT_TIMEOUT_S)
        new_passes, orig_passes = on_stub[0].passed, orig_stub[0].passed
        holds = not empty and new_passes and not orig_passes
        return OracleResult(
            holds,
            "reference solution: planted passes; "
            f"empty workspace: planted {'is refused' if empty else 'fails'}; "
            f"stub product: planted {_verb(new_passes)}, original {_verb(orig_passes)}",
        )


def _stub(check: bytes) -> dict[str, str]:
    """A product with no logic: each module the check imports from, defining each imported name
    as a function that returns None."""
    tree = _parse(check)
    modules: dict[str, dict[str, None]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import | ast.ImportFrom):
            for item in _product_imports([node]):
                names = modules.setdefault(item.module, {})
                if item.name:
                    names[item.name] = None
    if not modules:
        raise Inapplicable("the check imports nothing from the product, so there is no stub")
    return {
        f"{module}.py": "".join(
            f"def {name}(*args, **kwargs):\n    return None\n\n\n" for name in names
        )
        for module, names in modules.items()
    }


# --- under_specified --------------------------------------------------------------------------


def _drops(text: _Text, tree: ast.Module) -> list[tuple[int, int]]:
    """Byte ranges whose removal drops one assert or one test function and leaves valid Python:
    an assert alone on its lines in a block that keeps another statement, or a test function when
    another remains."""
    found: list[tuple[int, int]] = []
    functions = _test_functions(tree)
    for fn in functions:
        for block in _statement_lists(fn):
            if len(block) < 2:
                continue
            for stmt in block:
                if isinstance(stmt, ast.Assert) and text.owns_lines(stmt):
                    end_line = stmt.end_lineno or stmt.lineno
                    found.append((text.line_start(stmt.lineno), text.line_end(end_line)))
    # The block each test function sits in: the module, or its `Test*` class.
    parents = {id(fn): tree.body for fn in tree.body if _is_test(fn)}
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            parents |= {id(fn): node.body for fn in node.body if _is_test(fn)}
    if len(functions) >= 2:
        for fn in functions:
            if len(parents[id(fn)]) < 2:  # dropping it would leave an empty class: not Python
                continue
            first = fn.decorator_list[0].lineno if fn.decorator_list else fn.lineno
            start = text.line_start(first)
            # Take the blank lines above it too, so the spacing between the
            # functions that remain is the draft's own.
            while start > 0 and not text.data[text.starts_before(start) : start].strip(b" \t\n"):
                start = text.starts_before(start)
            found.append((start, text.line_end(fn.end_lineno or fn.lineno)))
    return sorted(set(found))


class UnderSpecified:
    name = "under_specified"

    def plant(self, original: bytes, rng: random.Random) -> bytes:
        tree = _parse(original)
        text = _Text(original)
        drops = _drops(text, tree)
        if not drops:
            raise Inapplicable(
                "no assert sits alone in a block with another statement, and the check has one "
                "test function"
            )
        start, end = rng.choice(drops)
        return text.splice(start, end, b"")

    def oracle(self, original: bytes, planted: bytes, file: str, task: BenchTask) -> OracleResult:
        if not task.mutants():
            raise Inapplicable(f"task {task.id} has no mutants to free")
        before = _kills(task, file, original)
        if before is None:
            raise Inapplicable("the reference solution already fails the draft's check")
        if not before:
            raise Inapplicable("the draft's check kills no mutant, so no drop can free one")
        after = _kills(task, file, planted)
        if after is None:
            return OracleResult(False, "the reference solution fails the planted check")
        freed = sorted(set(before) - set(after))
        holds = bool(freed)
        detail = (
            f"killed by the original, survive the planted check: {', '.join(freed)}"
            if freed
            else "no mutant the original killed survives the planted check"
        )
        return OracleResult(holds, detail)


@functools.lru_cache(maxsize=256)  # the same per-process cache as _wrong_on_reference
def _kills(task: BenchTask, file: str, data: bytes) -> tuple[str, ...] | None:
    """The mutants this one check kills, by bench/score.py `score_draft`; None when the reference
    solution fails it (a wrong check kills nothing that counts)."""
    with tempfile.TemporaryDirectory(prefix="boss_oracle_") as tmp:
        (Path(tmp) / file).write_bytes(data)
        score = score_draft(task, Path(tmp))
    return None if score.wrong else score.killed


def _verb(passed: bool) -> str:
    return "passes" if passed else "fails"
