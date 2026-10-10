"""Mutants of the lines a change touched, for the check strength of `antstreet audit check`.

A mutant is one small edit to the head's code, of the kind a wrong implementation makes: a
comparison or an operator flipped, a constant off by one, a condition negated, a `raise` dropped,
a returned value replaced by None. Only lines the change added or edited are mutated, in a fixed
order, so the same change gives the same mutants. Standard library `ast` only; comments and layout
are lost in a mutant, which is only ever run, never shown.

Some mutants change nothing a caller can see (an equivalent mutant): no check can kill those, so a
kill count is a measure of how much a check bites, never a catch rate.
"""

from __future__ import annotations

import ast
import difflib
import itertools
from collections.abc import Mapping
from dataclasses import dataclass

DEFAULT_CAP = 30

_SWAPS: dict[type[ast.AST], type[ast.AST]] = {
    ast.Lt: ast.LtE,
    ast.LtE: ast.Lt,
    ast.Gt: ast.GtE,
    ast.GtE: ast.Gt,
    ast.Eq: ast.NotEq,
    ast.NotEq: ast.Eq,
    ast.Is: ast.IsNot,
    ast.IsNot: ast.Is,
    ast.In: ast.NotIn,
    ast.NotIn: ast.In,
    ast.Add: ast.Sub,
    ast.Sub: ast.Add,
    ast.And: ast.Or,
    ast.Or: ast.And,
}
_SYMBOLS = {
    ast.Lt: "<", ast.LtE: "<=", ast.Gt: ">", ast.GtE: ">=", ast.Eq: "==", ast.NotEq: "!=",
    ast.Is: "is", ast.IsNot: "is not", ast.In: "in", ast.NotIn: "not in", ast.Add: "+",
    ast.Sub: "-", ast.And: "and", ast.Or: "or",
}  # fmt: skip


@dataclass(frozen=True, slots=True)
class Mutant:
    path: str  # relative to the tree, as given
    line: int  # in the head's file
    operator: str  # e.g. "< -> <="
    source: str  # the whole mutated file


@dataclass(frozen=True, slots=True)
class _Site:
    path: str
    line: int
    node: int  # index in `ast.walk` order of a fresh parse of the head's file
    sub: int  # which comparison operator, for a chained comparison
    operator: str


def changed_lines(old: str, new: str) -> set[int]:
    """The 1-based lines of `new` that `old` does not have at that place: added or edited."""
    matcher = difflib.SequenceMatcher(None, old.splitlines(), new.splitlines(), autojunk=False)
    return {
        j + 1
        for tag, _, _, j1, j2 in matcher.get_opcodes()
        if tag in ("replace", "insert")
        for j in range(j1, j2)
    }


def mutants(
    files: Mapping[str, tuple[str, str]], cap: int = DEFAULT_CAP
) -> tuple[list[Mutant], int]:
    """(at most `cap` mutants, how many there were before the cap) for `files`: path -> (base
    text, head text), the base text empty for a new file. A file that does not parse is skipped.
    Over the cap, mutants are taken evenly across the whole list, not the first files only."""
    sites: list[_Site] = []
    texts: dict[str, str] = {}
    for path in sorted(files):
        old, new = files[path]
        tree = _parse(new)
        if tree is None:
            continue
        texts[path] = new
        sites += _sites(path, tree, changed_lines(old, new))
    total = len(sites)
    if total > cap:
        sites = [sites[i * total // cap] for i in range(max(cap, 0))]
    return [_make(s, texts[s.path]) for s in sites], total


def _parse(text: str) -> ast.Module | None:
    try:
        return ast.parse(text)
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        return None


def _sites(path: str, tree: ast.Module, lines: set[int]) -> list[_Site]:
    found: list[_Site] = []
    for index, node in enumerate(ast.walk(tree)):
        line = getattr(node, "lineno", None)
        if line not in lines:
            continue

        def add(operator: str, sub: int = 0, at: int = index, ln: int = line) -> None:
            found.append(_Site(path, ln, at, sub, operator))

        if isinstance(node, ast.Compare):
            for sub, op in enumerate(node.ops):
                if type(op) in _SWAPS:
                    add(f"{_SYMBOLS[type(op)]} -> {_SYMBOLS[_SWAPS[type(op)]]}", sub)
        elif isinstance(node, ast.BinOp | ast.BoolOp) and type(node.op) in _SWAPS:
            add(f"{_SYMBOLS[type(node.op)]} -> {_SYMBOLS[_SWAPS[type(node.op)]]}")
        elif isinstance(node, ast.Constant) and isinstance(node.value, bool):
            add(f"{node.value} -> {not node.value}")
        elif isinstance(node, ast.Constant) and isinstance(node.value, int | float):
            add(f"{node.value!r} -> {node.value + 1!r}")
        elif isinstance(node, ast.Return) and node.value is not None:
            if not (isinstance(node.value, ast.Constant) and node.value.value is None):
                add("return value -> return None")
        elif isinstance(node, ast.Raise):
            add("raise -> pass")
        elif isinstance(node, ast.If):
            add("if condition -> if not condition")
    return found


def _make(site: _Site, text: str) -> Mutant:
    tree = ast.parse(text)
    node = next(itertools.islice(ast.walk(tree), site.node, None))
    if isinstance(node, ast.Compare):
        node.ops[site.sub] = _SWAPS[type(node.ops[site.sub])]()  # type: ignore[call-overload]
    elif isinstance(node, ast.BinOp | ast.BoolOp):
        node.op = _SWAPS[type(node.op)]()  # type: ignore[assignment]
    elif isinstance(node, ast.Constant) and isinstance(node.value, bool):
        node.value = not node.value
    elif isinstance(node, ast.Constant) and isinstance(node.value, int | float):
        node.value = node.value + 1
    elif isinstance(node, ast.Return):
        node.value = None
    elif isinstance(node, ast.If):
        node.test = ast.UnaryOp(ast.Not(), node.test)
    elif isinstance(node, ast.Raise):
        _replace(tree, node, ast.Pass())
    return Mutant(site.path, site.line, site.operator, ast.unparse(tree))


def _replace(tree: ast.AST, old: ast.stmt, new: ast.stmt) -> None:
    for parent in ast.walk(tree):
        for _, value in ast.iter_fields(parent):
            if isinstance(value, list) and any(item is old for item in value):
                value[[id(item) for item in value].index(id(old))] = new
                return
