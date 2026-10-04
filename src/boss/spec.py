"""The rules of a request, and whether the checks drafted for it cover them.

Code owns every character of the request. `split` cuts the idea into rules (one sentence each,
with offsets into the idea as given) and extracts the literals a test of each rule must contain.
A model only ever refers to a rule by its id, so it cannot paraphrase or invent one: the staged
draft that asked a model to quote the idea was refused 12 times in 17 for exactly that.

`verify` does not trust a claim that a check covers a rule. It reports the claim and, beside it,
whether the claiming checks contain what the rule names: a non-ASCII string, the name `float`, a
number as large as the rule's size, each literal of a list of examples. That is presence in the
check's syntax tree, not proof the check asserts the behaviour: `anchor_missing` is a strong flag
(that check cannot be testing it), `anchored` is weak evidence, and no function here runs a check
or calls a model.
"""

from __future__ import annotations

import ast
import bisect
import contextlib
import hashlib
import json
import re
from collections.abc import Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from boss.redact import safe_text

SPLITTER = "v1"
RULES_FILE = "rules.json"
MAX_IDEA_CHARS = 20_000  # longer ideas are covered per numbered item or paragraph
REFUSED_IDEA_CHARS = 200_000  # longer ideas are refused: a hostile one must not cost minutes
MAX_RULES = 40
MAX_RULES_PER_CHECK = 5
MAX_ANCHORS = 12  # per rule; a sentence naming more literals is not one rule
WAIVED_WARN_SHARE = 0.25
_SHOWN_CHARS = 160

KINDS = ("behaviour", "edge", "error", "format", "example", "context")
STATES = ("uncovered", "waived", "anchor_missing", "unanchored", "anchored", "context")
ANCHOR_TYPES = ("literal", "enum_item", "exception", "type", "magnitude", "non_ascii")
# The types that decide a rule's state and the headline. In the offline evaluation of 17 tasks a
# missing literal or list item was no better a sign of a real omission than chance (5% and 28% of
# flags right against a 22% base rate); these four were (71%, 100%, 100%, 29% on few flags) and
# one of them, a missing non-ASCII string, was the most common real omission. The others are still
# computed and shown, apart (docs/DECISIONS.md D38).
HEADLINE_TYPES = frozenset({"non_ascii", "exception", "magnitude", "type"})


class SpecError(ValueError):
    """The idea cannot be split rule by rule, or a stored rule list is not the idea's."""


@dataclass(frozen=True, slots=True)
class Anchor:
    type: str  # one of ANCHOR_TYPES
    value: str  # the literal, the exception or type name, or the number as text

    def __post_init__(self) -> None:
        if self.type not in ANCHOR_TYPES:
            raise ValueError(f"anchor type must be one of {ANCHOR_TYPES}, got {self.type!r}")


@dataclass(frozen=True, slots=True)
class Rule:
    id: str  # R01, R02, ... in idea order, assigned here and nowhere else
    group: str  # G0 is the text before the first numbered item; else the item's own number
    start: int  # offsets into the idea exactly as given
    end: int
    text: str  # idea[start:end]
    kind: str  # one of KINDS; a hint for display, never read by a decision
    anchors: tuple[Anchor, ...]

    @property
    def scored(self) -> bool:
        return self.kind != "context"


@dataclass(frozen=True, slots=True)
class Split:
    idea_sha256: str
    rules: tuple[Rule, ...]
    coarse: bool  # one rule per numbered item or paragraph, because the sentences were too many
    code_lines: int  # indented or fenced code that is neither a rule nor an anchor source

    def by_id(self) -> dict[str, Rule]:
        return {r.id: r for r in self.rules}

    @property
    def scorable(self) -> tuple[Rule, ...]:
        return tuple(r for r in self.rules if r.scored)


# --- splitting -------------------------------------------------------------------------------

_NUMBERED = re.compile(r"[ \t]{0,3}(\d{1,3})[.)][ \t]+")
_BULLET = re.compile(r"[ \t]{0,6}(?:[-*+•]|[A-Za-z][.)])[ \t]+")
_TICKS = re.compile(r"`[^`]{0,200}`")
_BLANK_LINE = re.compile(r"\n[ \t\r]*\n")
_BOUNDARY = re.compile(r"(?<=[.!?])\s+")
_ABBREVIATION = re.compile(r"(?:^|\s)(?:e\.g|i\.e|vs|cf|approx|etc|no|fig)\.$", re.I)
_ABBREVIATION_REACH = 9  # the longest abbreviation, "approx.", and the space before it
_SIGNATURE = re.compile(r"[\w.]+\([^()]*\)(?:\s*->\s*.+)?")
_WORD = re.compile(r"[A-Za-z]{2,}")

_ERROR = re.compile(r"\braise|Error\b|Exception\b|\binvalid\b|not valid|\brefus|\breject", re.I)
_EDGE = re.compile(
    r"\bempty\b|\bzero\b|\bnegative\b|at most|at least|exactly|\bfirst\b|\blast\b|"
    r"\bnever\b|\bonly\b|\bbelow\b|\babove\b|\bboundar|\bmaximum\b|\bminimum\b",
    re.I,
)
_FORMAT = re.compile(
    r"\bformat|\bseparator|\bwhitespace|\bupper|\blower|\bpadd|\bquot|\bescape", re.I
)
_EXAMPLE = re.compile(r"for example|\be\.g\.|such as|\bfor instance", re.I)


def split(idea: str) -> Split:
    """Cut `idea` into rules. Pure and deterministic; never raises for text of any content.

    Raises SpecError only when the idea is over REFUSED_IDEA_CHARS, or when even one rule per
    numbered item or paragraph would be more than MAX_RULES: a request that long is not covered
    rule by rule, and silently dropping part of it would hide exactly what the layer exists to
    show.
    """
    if len(idea) > REFUSED_IDEA_CHARS:
        raise SpecError(f"the idea is over {REFUSED_IDEA_CHARS} characters; split it into runs")
    blocks, code_lines, numbered = _blocks(idea)
    sentences: list[tuple[int, int, int]] = []  # start, end, group number
    for bstart, bend, group in blocks:
        sentences += [(s, e, group) for s, e in _sentences(idea, bstart, bend)]
    if not numbered:  # no numbered items: each paragraph is a group of its own
        sentences = _paragraph_groups(idea, sentences)
    coarse = len(sentences) > MAX_RULES or len(idea) > MAX_IDEA_CHARS
    if coarse:
        sentences = _per_group(sentences)
    if len(sentences) > MAX_RULES:
        raise SpecError(
            f"the idea has {len(sentences)} numbered items or paragraphs; rule-by-rule coverage "
            f"takes at most {MAX_RULES}. Shorten it or split it into several runs."
        )
    rules = []
    for n, (start, end, group) in enumerate(sentences, start=1):
        text = idea[start:end]
        context = group == 0 or _is_context(text)
        rules.append(
            Rule(
                id=f"R{n:02d}",
                group=f"G{group}",
                start=start,
                end=end,
                text=text,
                kind="context" if context else _kind(text),
                anchors=() if context else extract_anchors(text),
            )
        )
    sha = hashlib.sha256(idea.encode("utf-8", errors="surrogatepass")).hexdigest()
    return Split(sha, tuple(rules), coarse, code_lines)


def _blocks(idea: str) -> tuple[list[tuple[int, int, int]], int, bool]:
    """Text blocks as (start, end, group number), the number of code lines skipped, and whether
    the idea has numbered items. A block is one paragraph, numbered item or bullet; the text of a
    block is contiguous in the idea, so offsets into it are offsets into the idea."""
    blocks: list[tuple[int, int, int]] = []
    group, code_lines, numbered = 0, 0, False
    current: list[int] | None = None  # [start, end] of the block being read
    in_fence = False
    prev = "blank"  # blank | code | text

    def close() -> None:
        nonlocal current
        if current is not None:
            blocks.append((current[0], current[1], group))
        current = None

    position = 0
    for line in idea.split("\n"):
        start, end = position, position + len(line)
        position = end + 1
        body = line.rstrip()
        text = body.strip()
        if text.startswith("```"):
            close()
            in_fence = not in_fence
            prev = "code"
            continue
        if in_fence:
            code_lines += 1
            prev = "code"
            continue
        if not text:
            close()
            prev = "blank"
            continue
        indented = line.startswith(("    ", "\t"))
        marker = _NUMBERED.match(line)
        if marker is None and indented and prev in ("blank", "code") and not _is_prose(text):
            close()
            code_lines += 1
            prev = "code"
            continue
        if marker is not None:
            close()
            group, numbered = int(marker[1]), True
            current = [start + marker.end(), start + len(body)]
        elif (bullet := _BULLET.match(line)) is not None:
            close()
            current = [start + bullet.end(), start + len(body)]
        elif current is None:
            current = [start + (len(line) - len(line.lstrip())), start + len(body)]
        else:
            current[1] = start + len(body)
        prev = "text"
    close()
    return blocks, code_lines, numbered


def _is_prose(text: str) -> bool:
    return text[-1] in ".!?:" or len(_WORD.findall(text)) >= 8


def _sentences(idea: str, start: int, end: int) -> list[tuple[int, int]]:
    """Sentence spans inside idea[start:end]. A boundary is `.`, `!` or `?` and white space
    followed by something that can start a sentence; never inside a backtick span, never after
    an abbreviation, never before a lower-case letter."""
    # kn: English sentence punctuation only; add terminators for another script when one appears
    block = idea[start:end]
    ticks = [(m.start(), m.end()) for m in _TICKS.finditer(block)]
    starts = [a for a, _ in ticks]
    cuts = [0]
    for m in _BOUNDARY.finditer(block):
        nxt = block[m.end() : m.end() + 1]
        if not nxt or nxt.islower():
            continue
        i = bisect.bisect_left(starts, m.start()) - 1  # the last span that starts before the cut
        if i >= 0 and m.start() < ticks[i][1]:
            continue
        if _ABBREVIATION.search(block, max(0, m.start() - _ABBREVIATION_REACH), m.start()):
            continue
        cuts.append(m.end())
    spans = []
    for a, b in zip(cuts, [*cuts[1:], len(block)], strict=True):
        piece = block[a:b]
        text = piece.strip()
        if text and any(c.isalpha() for c in text):
            lead = len(piece) - len(piece.lstrip())
            spans.append((start + a + lead, start + a + lead + len(text)))
    return spans


def _paragraph_groups(
    idea: str, sentences: list[tuple[int, int, int]]
) -> list[tuple[int, int, int]]:
    """Group numbers for an idea with no numbered items: a blank line starts the next group."""
    out, group, previous_end = [], 1, 0
    for n, (start, end, _) in enumerate(sentences):
        if n and _BLANK_LINE.search(idea, previous_end, start):
            group += 1
        out.append((start, end, group))
        previous_end = end
    return out


def _per_group(sentences: list[tuple[int, int, int]]) -> list[tuple[int, int, int]]:
    out: list[tuple[int, int, int]] = []
    for start, end, group in sentences:
        if out and out[-1][2] == group:
            out[-1] = (out[-1][0], end, group)
        else:
            out.append((start, end, group))
    return out


def _is_context(text: str) -> bool:
    """Not a behaviour: a heading such as "Input text:", or a bare signature."""
    plain = " ".join(text.replace("`", "").split())
    if plain.endswith(":") and len(plain) <= 80:
        return True
    return bool(_SIGNATURE.fullmatch(plain))


def _kind(text: str) -> str:
    if _EXAMPLE.search(text) and _TICKS.search(text):
        return "example"
    for kind, pattern in (("error", _ERROR), ("edge", _EDGE), ("format", _FORMAT)):
        if pattern.search(text):
            return kind
    return "behaviour"


# --- anchors ---------------------------------------------------------------------------------

_EXCEPTION = re.compile(r"\b[A-Z][A-Za-z]*(?:Error|Exception)\b")
_TYPES = frozenset({"float", "int", "str", "bool", "list", "tuple", "dict", "set", "bytes"})
_NON_ASCII = re.compile(
    r"non-?\s?ASCII|not ASCII|\bASCII\b|other script|another script|full-?width|Arabic-Indic|"
    r"non-Latin",
    re.I,
)
_UNITS = (
    r"operands?|elements?|items?|nodes?|levels?|characters?|chars|deep|nested|entries|times|"
    r"iterations|steps|rows|columns|digits|lines|keys|bytes|calls|operations|tokens|words|"
    r"edges|vertices|numbers|terms|groups|segments|values"
)
_MAGNITUDE = re.compile(
    rf"(?:\b(?:at least|at most|up to|more than|over|about)\s+(?P<a>\d[\d,_]*)\b|"
    rf"\b(?P<b>\d[\d,_]*)\s+(?:\w+\s+){{0,2}}?(?:{_UNITS})\b)",
    re.I,
)
_MIN_MAGNITUDE = 50
_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_.]*")


def extract_anchors(text: str) -> tuple[Anchor, ...]:
    """What a test of this rule must contain, read from the rule's own words. Duplicates are
    dropped, order follows the text, and at most MAX_ANCHORS are kept."""
    found: dict[Anchor, None] = {}
    spans = [m[0][1:-1] for m in _TICKS.finditer(text)]
    literals = [s.strip() for s in spans if _is_literal(s.strip())]
    kind = "enum_item" if len(literals) >= 3 else "literal"
    for value in literals:
        found[Anchor(kind, value)] = None
    for m in _EXCEPTION.finditer(text):
        found[Anchor("exception", m[0])] = None
    for m in _TICKS.finditer(text):
        if m[0][1:-1].strip() in _TYPES and _states_a_result_type(text[: m.start()]):
            found[Anchor("type", m[0][1:-1].strip())] = None
    outside = _TICKS.sub(" ", text)
    for m in _MAGNITUDE.finditer(outside):
        number = _to_int(m["a"] or m["b"])
        if number is not None and number >= _MIN_MAGNITUDE:
            found[Anchor("magnitude", str(number))] = None
    if _NON_ASCII.search(text):
        found[Anchor("non_ascii", "non-ASCII")] = None
    return tuple(found)[:MAX_ANCHORS]


def _states_a_result_type(before: str) -> bool:
    """Whether a type named in backticks is a type the code under test returns ("returns a
    `float`", "the result is an `int`"), not one it is given ("a non-string argument (`bytes`)"):
    only the former is something a test must assert on, and the latter is noise if demanded."""
    near = before[-45:]
    said = re.search(
        r"\b(?:return\w*|result\w*|is an?|as an?|gives?|yields?|produces?)\b[^.]*$", near
    )
    return bool(said) and not re.search(r"\b(?:not an?|non-|argument|input)\b", near)


def _is_literal(span: str) -> bool:
    """A backtick span that is data a test would contain, not a name, signature or placeholder."""
    if not span or "..." in span or "…" in span or "->" in span:
        return False
    if _IDENTIFIER.fullmatch(span) or span in _TYPES:
        return False
    if not any(c.isalnum() for c in span) and not _evaluates(span):
        return False  # an operator or punctuation mark, named, not meant as test data
    if _SIGNATURE.fullmatch(span) or re.fullmatch(r"<[^<>]*>", span):
        return False
    return not re.fullmatch(r"[A-Za-z0-9]-[A-Za-z0-9]", span)  # a character range, not data


def _evaluates(span: str) -> bool:
    try:
        ast.literal_eval(span)
    except (ValueError, SyntaxError, MemoryError, RecursionError):
        return False
    return True


def _to_int(raw: str | None) -> int | None:
    if raw is None:
        return None
    digits = raw.replace(",", "").replace("_", "")
    return int(digits) if digits.isdigit() and len(digits) <= 15 else None


@dataclass(frozen=True, slots=True)
class Facts:
    """What a check's syntax tree contains, with docstrings and comments left out."""

    strings: tuple[str, ...]
    numbers: tuple[int | float, ...]
    values: tuple[Any, ...]  # every literal-evaluable node: lists, tuples, dicts, constants
    names: frozenset[str]

    @property
    def biggest(self) -> float:
        return max((abs(n) for n in self.numbers), default=0)

    @property
    def has_non_ascii(self) -> bool:
        return any(ord(c) > 0x7F for s in self.strings for c in s)


_MAX_NODES = 20_000
_MAX_FOLD = 10**18
_BINOPS = (ast.Mult, ast.Add, ast.Sub, ast.FloorDiv, ast.Pow)


def facts(source: str) -> Facts | None:
    """The facts of one check file, or None when it does not parse."""
    try:
        tree = ast.parse(source.lstrip("﻿"))
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        return None
    docstrings = {id(d) for d in _docstrings(tree)}
    strings: list[str] = []
    numbers: list[int | float] = []
    values: list[Any] = []
    names: set[str] = set()
    for count, node in enumerate(ast.walk(tree)):
        if count > _MAX_NODES:
            break
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.alias):
            names.add(node.name.rsplit(".", 1)[-1])
        elif isinstance(node, ast.Constant) and id(node) in docstrings:
            continue
        number = _fold(node, 0)
        if number is not None:
            numbers.append(number)
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            strings.append(node.value)
        if isinstance(node, ast.Constant | ast.List | ast.Tuple | ast.Dict | ast.Set):
            with contextlib.suppress(
                ValueError, TypeError, SyntaxError, MemoryError, RecursionError
            ):
                values.append(ast.literal_eval(node))
    return Facts(tuple(strings), tuple(numbers), tuple(values), frozenset(names))


def _docstrings(tree: ast.Module) -> list[ast.expr]:
    found: list[ast.expr] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            first = node.body[0] if node.body else None
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                found.append(first.value)
    return found


def _fold(node: ast.AST, depth: int) -> int | float | None:
    """A number, or a product, sum or power of numbers, bounded so a hostile check cannot make
    this slow or huge."""
    if depth > 8:
        return None
    if isinstance(node, ast.Constant):
        v = node.value
        if isinstance(v, bool) or not isinstance(v, int | float):
            return None
        return v if abs(v) <= _MAX_FOLD else None
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        inner = _fold(node.operand, depth + 1)
        return None if inner is None else -inner
    if isinstance(node, ast.BinOp) and isinstance(node.op, _BINOPS):
        left, right = _fold(node.left, depth + 1), _fold(node.right, depth + 1)
        if left is None or right is None:
            return None
        try:
            if isinstance(node.op, ast.Pow):
                if abs(right) > 64 or abs(left) > 10**6:
                    return None
                result = left**right
            elif isinstance(node.op, ast.Mult):
                result = left * right
            elif isinstance(node.op, ast.Add):
                result = left + right
            elif isinstance(node.op, ast.Sub):
                result = left - right
            else:
                result = left // right
        except (ZeroDivisionError, OverflowError, ValueError):
            return None
        return result if isinstance(result, int | float) and abs(result) <= _MAX_FOLD else None
    return None


def present(anchor: Anchor, found: Iterable[Facts]) -> bool:
    """Whether any of the checks' facts satisfies the anchor."""
    # kn: presence in the syntax tree, not proof the check asserts it; a mutation pass is proof
    checks = list(found)
    if anchor.type == "non_ascii":
        return any(f.has_non_ascii for f in checks)
    if anchor.type in ("exception", "type"):
        return any(anchor.value in f.names for f in checks)
    if anchor.type == "magnitude":
        return any(f.biggest >= int(anchor.value) for f in checks)
    return any(_has_literal(anchor.value, f) for f in checks)


def _has_literal(raw: str, found: Facts) -> bool:
    short = len(raw) <= 1  # a one-character literal is in almost any string
    if any((s == raw) if short else (raw in s) for s in found.strings):
        return True
    try:
        parsed = ast.literal_eval(raw)
    except (ValueError, SyntaxError, MemoryError, RecursionError):
        return False
    if isinstance(parsed, str):
        return (
            any(s == parsed for s in found.strings)
            if len(parsed) <= 1
            else any(parsed in s for s in found.strings)
        )
    if type(parsed) in (int, float):
        return any(type(n) in (int, float) and n == parsed for n in found.numbers)
    return any(type(v) is type(parsed) and v == parsed for v in found.values)


def missing(anchors: Iterable[Anchor], found: Sequence[Facts]) -> tuple[Anchor, ...]:
    return tuple(a for a in anchors if not present(a, found))


def draft_gaps(
    split_: Split, sources: Mapping[str, str], types: Collection[str] | None = None
) -> dict[str, tuple[Anchor, ...]]:
    """For each scored rule with anchors, those no check of the draft contains. This is the
    union form, for a draft written without claims: a rule is listed when nothing in the whole
    draft could be testing it. All anchor types by default, which is what the offline evaluation
    measured; pass `types` (e.g. HEADLINE_TYPES) to look at some."""
    parsed = [f for f in (facts(s) for s in sources.values()) if f is not None]
    gaps = {}
    for rule in split_.scorable:
        wanted = [a for a in rule.anchors if types is None or a.type in types]
        if wanted and (lost := missing(wanted, parsed)):
            gaps[rule.id] = lost
    return gaps


# --- verifying claims ------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RuleStatus:
    rule: str
    state: str  # one of STATES
    checks: tuple[str, ...]  # checks claiming the rule
    missing: tuple[Anchor, ...]  # headline anchors no claiming check contains
    unscored: tuple[Anchor, ...] = ()  # literal and list-item anchors no claiming check contains


@dataclass(frozen=True, slots=True)
class SpecReport:
    split: Split
    statuses: tuple[RuleStatus, ...]
    problems: tuple[str, ...]  # a structure a draft must not have; the caller refuses it
    warnings: tuple[str, ...]
    unreadable: tuple[str, ...]  # claiming checks that do not parse

    def count(self, state: str) -> int:
        return sum(1 for s in self.statuses if s.state == state)

    @property
    def scorable(self) -> int:
        return len(self.split.scorable)

    @property
    def claimed(self) -> int:
        return sum(self.count(s) for s in ("anchored", "unanchored", "anchor_missing"))

    @property
    def with_unscored_missing(self) -> int:
        return sum(1 for s in self.statuses if s.unscored)

    @property
    def headline(self) -> float:
        """Anchored rules over scorable rules. Unanchored, waived and uncovered rules count
        against it: an unverifiable claim is not verified."""
        return self.count("anchored") / self.scorable if self.scorable else 0.0

    def to_summary(self) -> dict[str, Any]:
        return {
            "rules_sha256": rules_digest(self.split),
            "rules": self.scorable,
            "anchored": self.count("anchored"),
            "unanchored": self.count("unanchored"),
            "anchor_missing": self.count("anchor_missing"),
            "unscored_missing": self.with_unscored_missing,
            "uncovered": [s.rule for s in self.statuses if s.state == "uncovered"],
            "waived": [s.rule for s in self.statuses if s.state == "waived"],
        }


def verify(
    split_: Split,
    claims: Mapping[str, Sequence[str]],
    sources: Mapping[str, str],
    waived: Mapping[str, str] | None = None,
) -> SpecReport:
    """Check a draft's claims against the rules and the check files.

    `claims` maps a check id to the rule ids it says it covers, `sources` a check id to its file
    text, `waived` a rule id to the boss's reason for leaving it untested. Nothing is run.
    """
    waived = dict(waived or {})
    by_id = split_.by_id()
    problems: list[str] = []
    claimed_by: dict[str, list[str]] = {r: [] for r in by_id}
    for check, cited in claims.items():
        if not cited:
            problems.append(f"check {check} cites no rule")
        if len(cited) > MAX_RULES_PER_CHECK:
            problems.append(
                f"check {check} cites {len(cited)} rules; at most {MAX_RULES_PER_CHECK}"
            )
        if len(set(cited)) != len(cited):
            problems.append(f"check {check} cites a rule twice")
        for rule_id in dict.fromkeys(cited):
            if rule_id not in by_id:
                problems.append(f"check {check} cites unknown rule {rule_id!r}")
            else:
                claimed_by[rule_id].append(check)
    for rule_id in waived:
        if rule_id not in by_id:
            problems.append(f"untested names unknown rule {rule_id!r}")
        elif claimed_by[rule_id]:
            problems.append(f"{rule_id} is cited by {', '.join(claimed_by[rule_id])} and untested")
    parsed: dict[str, Facts | None] = {}
    unreadable: list[str] = []
    statuses = []
    for rule in split_.rules:
        checks = tuple(claimed_by[rule.id])
        if not rule.scored:
            statuses.append(RuleStatus(rule.id, "context", checks, ()))
        elif not checks:
            state = "waived" if rule.id in waived else "uncovered"
            statuses.append(RuleStatus(rule.id, state, (), ()))
        else:
            for c in checks:
                if c not in parsed:
                    parsed[c] = facts(sources[c]) if c in sources else None
                    if parsed[c] is None:
                        unreadable.append(c)
            found = [f for c in checks if (f := parsed[c]) is not None]
            counted = [a for a in rule.anchors if a.type in HEADLINE_TYPES]
            others = [a for a in rule.anchors if a.type not in HEADLINE_TYPES]
            lost = missing(counted, found)
            state = "anchor_missing" if lost else ("anchored" if counted else "unanchored")
            statuses.append(RuleStatus(rule.id, state, checks, lost, missing(others, found)))
    warnings = []
    count_waived = sum(1 for s in statuses if s.state == "waived")
    scorable = len(split_.scorable)
    if scorable and count_waived / scorable > WAIVED_WARN_SHARE:
        warnings.append(f"the boss left {count_waived} of {scorable} rules untested")
    if split_.coarse:
        warnings.append(
            "the idea is long: coverage is per numbered item or paragraph, not sentence"
        )
    return SpecReport(
        split_, tuple(statuses), tuple(problems), tuple(warnings), tuple(dict.fromkeys(unreadable))
    )


def _line(text: str) -> str:
    return safe_text(" ".join(text.split()), limit=_SHOWN_CHARS)


def render_report(report: SpecReport, reasons: Mapping[str, str] | None = None) -> str:
    """The investor's view, uncovered rules first. Rule text is the idea's own, made safe to
    show; the only model text is a waiver's reason, shown on one line and labelled."""
    reasons = reasons or {}
    rules = report.split.by_id()
    n = report.scorable
    head = (
        f"SPEC COVERAGE  rules {n} | UNCOVERED {report.count('uncovered')} | "
        f"anchored {report.count('anchored')} | unanchored {report.count('unanchored')} | "
        f"anchor-missing {report.count('anchor_missing')} | waived {report.count('waived')}  "
        f"(anchored {report.headline:.0%}; claimed {report.claimed}/{n})"
    )
    lines = [head, *(f"WARNING: {w}" for w in report.warnings)]
    lines += [f"PROBLEM: {_line(p)}" for p in report.problems]

    def section(title: str, state: str) -> None:
        picked = [s for s in report.statuses if s.state == state]
        if not picked:
            return
        lines.append(title)
        for s in picked:
            r = rules[s.rule]
            tail = ""
            if state == "anchor_missing":
                tail = f"  -> {','.join(s.checks)}: {', '.join(_describe(a) for a in s.missing)}"
            elif state in ("anchored", "unanchored"):
                tail = f"  -> {','.join(s.checks)}"
            elif state == "waived":
                tail = f"  (boss, unverified: {_line(reasons.get(s.rule, 'no reason'))})"
            lines.append(f"  {s.rule} [{r.kind}] {_line(r.text)}{tail}")

    section("UNCOVERED (no check cites these; nothing will test them):", "uncovered")
    section("CLAIMED, BUT THE CHECK CANNOT BE TESTING IT (anchor missing):", "anchor_missing")
    section("WAIVED BY THE BOSS (model text, not verified):", "waived")
    section("COVERED, NOTHING TO VERIFY (no anchor in the rule):", "unanchored")
    section("COVERED, ANCHORS PRESENT (presence only, not proof):", "anchored")
    shown = [s for s in report.statuses if s.unscored]
    if shown:
        lines.append(
            "LITERALS THE CHECKS DO NOT CONTAIN (shown, not scored: in the offline evaluation a "
            "missing literal was no better a sign of an omission than chance):"
        )
        for s in shown:
            lost = ", ".join(_describe(a) for a in s.unscored)
            lines.append(f"  {s.rule} -> {','.join(s.checks)}: {lost}")
    if report.unreadable:
        lines.append(f"UNREADABLE CHECKS (do not parse): {', '.join(report.unreadable)}")
    return "\n".join(lines)


def _describe(anchor: Anchor) -> str:
    return {
        "non_ascii": "no non-ASCII text",
        "exception": f"no {anchor.value}",
        "type": f"no {anchor.value} (name)",
        "magnitude": f"no number >= {anchor.value}",
    }.get(anchor.type, f"no {_line(anchor.value)}")


# --- the stored rule list --------------------------------------------------------------------


def to_data(split_: Split) -> dict[str, Any]:
    return {
        "splitter": SPLITTER,
        "idea_sha256": split_.idea_sha256,
        "coarse": split_.coarse,
        "code_lines": split_.code_lines,
        "rules": [
            {
                "id": r.id,
                "group": r.group,
                "start": r.start,
                "end": r.end,
                "text": r.text,
                "kind": r.kind,
                "anchors": [{"type": a.type, "value": a.value} for a in r.anchors],
            }
            for r in split_.rules
        ],
    }


def rules_digest(split_: Split) -> str:
    text = json.dumps(to_data(split_), sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(text.encode("ascii")).hexdigest()


def dumps(split_: Split) -> str:
    return json.dumps(to_data(split_), indent=2, ensure_ascii=True)


def load(path: Path, idea: str) -> Split:
    """The stored rule list, accepted only if it is what `split` makes of `idea` today. A rule
    list edited to drop a rule, or written for another idea or splitter, is SpecError."""
    try:
        stored = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SpecError(f"cannot read {path.name}: {exc}") from exc
    fresh = split(idea)
    if stored != json.loads(dumps(fresh)):
        raise SpecError(
            f"{path.name} is not the rule list of this idea (edited, or made by another splitter)"
        )
    return fresh
