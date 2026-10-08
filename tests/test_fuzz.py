"""Seeded fuzz and property tests. Every generator takes a fixed seed, so a failure reproduces."""

import json
import math
import random
import string
from datetime import UTC, datetime
from pathlib import Path

import pytest

from antstreet import held_out
from antstreet.approval import NotApprovedError, content_hashes, require_approval
from antstreet.bench.table import wilson_interval
from antstreet.cli import usd_arg
from antstreet.errors import INFRASTRUCTURE, Outcome, classify
from antstreet.ledger import (
    LEDGER_VERSION,
    Billing,
    Event,
    EventType,
    LedgerCorruptError,
    LedgerWriter,
    Totals,
    read_events,
    total,
    totals_by,
)
from antstreet.redact import redact
from antstreet.rule import Decision, FiringPolicy, SliceRecord, decide
from antstreet.stream import StreamReader
from antstreet.termsheet import CheckSpec, Round, Task, TermSheet, TermSheetError
from antstreet.worker import usd

FIXTURES = Path(__file__).parent / "fixtures"
FIXTURE_LINES = [
    line
    for f in sorted(FIXTURES.glob("*.jsonl"))
    for line in f.read_text(encoding="utf-8").splitlines()
    if line.strip()
]
TEXT_ALPHABET = string.printable + "é☃ \u0000"


def rand_text(rng: random.Random, max_len: int = 12, alphabet: str = TEXT_ALPHABET) -> str:
    return "".join(rng.choice(alphabet) for _ in range(rng.randint(0, max_len)))


def rand_json(rng: random.Random, depth: int = 0) -> object:
    kinds = ["null", "bool", "int", "float", "str"] + (["list", "dict"] if depth < 3 else [])
    kind = rng.choice(kinds)
    match kind:
        case "null":
            return None
        case "bool":
            return rng.random() < 0.5
        case "int":
            return rng.choice([0, 1, -1, rng.randint(-(10**6), 10**6), rng.randint(0, 10**30)])
        case "float":
            return rng.uniform(-1e6, 1e6)
        case "str":
            return rand_text(rng)
        case "list":
            return [rand_json(rng, depth + 1) for _ in range(rng.randint(0, 3))]
        case _:
            return {rand_text(rng, 6): rand_json(rng, depth + 1) for _ in range(rng.randint(0, 3))}


# 1. ledger -------------------------------------------------------------------------------------

ACTORS = ["boss", "gate", "rule", "investor"]
LEDGER_EVENTS = 300
LEDGER_CORRUPTIONS = 400


def rand_event(rng: random.Random) -> Event:
    actor = rng.choice(
        ACTORS + [f"worker:{rand_text(rng, 8, string.ascii_letters + string.digits + '_-') or 'w'}"]
    )
    ts = datetime.fromtimestamp(rng.randint(0, 2**32), UTC).isoformat()
    return Event(
        run=rand_text(rng, 10, string.ascii_letters + string.digits) or "r",
        round=rng.randint(0, 50),
        actor=actor,
        event=rng.choice(list(EventType)),
        cost_micros=rng.choice([None, 0, rng.randint(0, 10**9), rng.randint(0, 10**15)]),
        tokens_in=rng.randint(0, 10**6),
        tokens_out=rng.randint(0, 10**6),
        tokens_cached=rng.randint(0, 10**6),
        billing=rng.choice(list(Billing)),
        data={rand_text(rng, 6): rand_json(rng) for _ in range(rng.randint(0, 4))},
        ts=ts,
    )


def assert_valid_event(e: Event) -> None:
    assert type(e) is Event
    assert type(e.run) is str and e.run
    assert type(e.round) is int and e.round >= 0
    assert type(e.actor) is str
    assert e.actor in ACTORS or e.actor.startswith("worker:")
    assert type(e.event) is EventType
    assert e.cost_micros is None or (type(e.cost_micros) is int and e.cost_micros >= 0)
    for n in (e.tokens_in, e.tokens_out, e.tokens_cached):
        assert type(n) is int and n >= 0
    assert type(e.billing) is Billing
    assert type(e.data) is dict
    assert type(e.ts) is str


def test_ledger_event_json_round_trip():
    rng = random.Random(1001)
    for _ in range(LEDGER_EVENTS * 3):
        e = rand_event(rng)
        again = Event.from_json(e.to_json())
        assert again == e
        assert_valid_event(again)


def test_ledger_writer_reader_totals(tmp_path):
    rng = random.Random(1002)
    for i in range(3):
        events = [rand_event(rng) for _ in range(LEDGER_EVENTS // 3)]
        path = tmp_path / f"ledger{i}.jsonl"
        with LedgerWriter(path) as w:
            for e in events:
                w.append(e)
        assert read_events(path) == events

        want = Totals(
            cost_micros=sum(e.cost_micros or 0 for e in events),
            unknown_cost_events=sum(e.cost_micros is None for e in events),
            tokens_in=sum(e.tokens_in for e in events),
            tokens_out=sum(e.tokens_out for e in events),
            tokens_cached=sum(e.tokens_cached for e in events),
            events=len(events),
        )
        assert total(events) == want

        groups = totals_by(events, lambda e: e.actor)
        assert set(groups) == {e.actor for e in events}
        for field in Totals.__dataclass_fields__:
            assert sum(getattr(g, field) for g in groups.values()) == getattr(want, field)
        for actor, g in groups.items():
            assert g == total(e for e in events if e.actor == actor)


def _truncate(rng, raw):
    return json.dumps(raw)[: rng.randint(0, len(json.dumps(raw)))]


def _flip(rng, raw):
    line = json.dumps(raw)
    i = rng.randrange(len(line))
    return line[:i] + rng.choice(TEXT_ALPHABET) + line[i + 1 :]


def _drop_key(rng, raw):
    return json.dumps({k: v for k, v in raw.items() if k != rng.choice(sorted(raw))})


def _add_key(rng, raw):
    return json.dumps({**raw, rand_text(rng, 5) or "x": rand_json(rng)})


def _change_type(rng, raw):
    return json.dumps({**raw, rng.choice(sorted(raw)): rand_json(rng)})


def _wrong_version(rng, raw):
    return json.dumps(
        {**raw, "v": rng.choice([0, 2, -1, "1", 1.5, None, True, [1], LEDGER_VERSION + 1])}
    )


@pytest.mark.parametrize(
    "corrupt",
    [
        _truncate,
        _flip,
        _drop_key,
        _add_key,
        _change_type,
        _wrong_version,
    ],
)
def test_ledger_corruption_is_valid_or_ledger_corrupt(corrupt, tmp_path):
    rng = random.Random(1003)
    path = tmp_path / "ledger.jsonl"
    for _ in range(LEDGER_CORRUPTIONS):
        raw = json.loads(rand_event(rng).to_json())
        path.write_text(corrupt(rng, raw) + "\n", encoding="utf-8")
        try:
            events = read_events(path)
        except LedgerCorruptError:
            continue
        for e in events:
            assert_valid_event(e)


# 2. stream -------------------------------------------------------------------------------------

STREAM_RUNS = 600


def check_reader_usage(reader: StreamReader) -> None:
    u = reader.usage()
    for n in (u.tokens_in, u.tokens_out, u.tokens_cached):
        assert type(n) is int
    assert u.cost_micros is None or (type(u.cost_micros) is int and u.cost_micros >= 0)


def junk_line(rng: random.Random, kind: str) -> str:
    match kind:
        case "bytes":
            return bytes(rng.randrange(256) for _ in range(rng.randint(0, 60))).decode(
                "utf-8", errors="replace"
            )
        case "json":
            return json.dumps(rand_json(rng))
        case "truncated":
            line = rng.choice(FIXTURE_LINES)
            return line[: rng.randint(0, len(line))]
        case _:  # digit_run: longer than Python's 4300-digit int-parsing limit
            return "".join(rng.choice(string.digits) for _ in range(rng.randint(4400, 5000)))


@pytest.mark.parametrize(
    "kind",
    [
        "bytes",
        "json",
        "truncated",
        "digit_run",
    ],
)
def test_stream_feed_never_raises_and_usage_is_typed(kind):
    rng = random.Random(2001)
    for _ in range(STREAM_RUNS // 4):
        reader = StreamReader()
        for _ in range(rng.randint(1, 8)):
            reader.feed(junk_line(rng, kind))
        check_reader_usage(reader)
        classify(reader.signals())


def mutate_result(rng: random.Random, result: dict) -> dict:
    result = json.loads(json.dumps(result))
    specials = [math.nan, math.inf, -math.inf, 1e308, -1, 2**70, "12", True, None, [], {}]
    target = result
    by_model = result.get("modelUsage")
    if isinstance(by_model, dict) and by_model and rng.random() < 0.6:
        target = rng.choice(list(by_model.values()))
    key = rng.choice(sorted(target)) if target else "total_cost_usd"
    target[key] = rng.choice([*specials, rand_json(rng)])
    return result


def test_stream_result_shaped_mutants_keep_usage_typed():
    rng = random.Random(2002)
    results = [json.loads(line) for line in FIXTURE_LINES if '"type": "result"' in line]
    assert results
    for _ in range(STREAM_RUNS):
        reader = StreamReader()
        reader.feed(json.dumps(mutate_result(rng, rng.choice(results))))
        check_reader_usage(reader)
        classify(reader.signals())


def rand_junk(rng: random.Random) -> str:
    kind = rng.choice(["bytes", "json", "truncated"])
    line = junk_line(rng, kind)
    if kind == "json":
        value = json.loads(line)
        if isinstance(value, dict):
            value.pop("type", None)  # a junk `type` would be a legitimate event, not junk
            line = json.dumps(value)
    return line


def test_stream_junk_lines_do_not_change_the_outcome():
    rng = random.Random(2003)
    for fixture in sorted(FIXTURES.glob("*.jsonl")):
        lines = fixture.read_text(encoding="utf-8").splitlines()
        clean = StreamReader()
        for line in lines:
            clean.feed(line)
        for _ in range(STREAM_RUNS // 6):
            noisy = StreamReader()
            for line in lines:
                for _ in range(rng.choice([0, 0, 1, 2])):
                    noisy.feed(rand_junk(rng))
                noisy.feed(line)
            noisy.feed(rand_junk(rng))
            assert noisy.usage() == clean.usage()
            assert noisy.session_id == clean.session_id
            assert noisy.status == clean.status
            assert classify(noisy.signals()) == classify(clean.signals())


# 3. redact -------------------------------------------------------------------------------------

REDACT_RUNS = 500
ALNUM = string.ascii_letters + string.digits
SECRET_MAKERS = {
    "sk-ant": lambda rng: "sk-ant-" + "".join(rng.choices(ALNUM, k=30)),
    "ghp": lambda rng: "ghp_" + "".join(rng.choices(ALNUM, k=36)),
    "aws": lambda rng: "AKIA" + "".join(rng.choices(string.ascii_uppercase + string.digits, k=16)),
    "bearer": lambda rng: "Bearer " + "".join(rng.choices(ALNUM, k=24)),
}
PRINTABLE = string.printable


def mixed_body(rng: random.Random, k: int) -> str:
    # A random key body almost always has a digit, an upper and a lower case letter; force it.
    body = rng.choices(ALNUM, k=k - 3) + [
        rng.choice(string.digits),
        rng.choice(string.ascii_uppercase),
        rng.choice(string.ascii_lowercase),
    ]
    rng.shuffle(body)
    return "".join(body)


SECRET_MAKERS["sk-bare"] = lambda rng: "sk-" + mixed_body(rng, rng.randint(20, 60))
SECRET_MAKERS["sk-bare-hyphen"] = lambda rng: (
    "sk-" + mixed_body(rng, 20) + "-" + mixed_body(rng, 20)
)


def embed(rng: random.Random, text: str, secret: str) -> str:
    i = rng.randint(0, len(text))
    return text[:i] + secret + text[i:]


def test_redact_is_idempotent():
    rng = random.Random(3001)
    for _ in range(REDACT_RUNS):
        text = rand_text(rng, 80, PRINTABLE)
        for _ in range(rng.randint(0, 3)):
            text = embed(rng, text, rng.choice(list(SECRET_MAKERS.values()))(rng))
        once = redact(text)
        assert redact(once) == once


@pytest.mark.parametrize("shape", SECRET_MAKERS)
def test_redact_masks_secret_shaped_strings_at_random_positions(shape):
    rng = random.Random(3002)
    for _ in range(REDACT_RUNS):
        text = rand_text(rng, 80, PRINTABLE)
        secret = SECRET_MAKERS[shape](rng)
        out = redact(embed(rng, text, secret))
        assert secret.removeprefix("Bearer ") not in out


@pytest.mark.parametrize("shape", SECRET_MAKERS)
def test_redact_masks_secret_shaped_strings_between_non_word_characters(shape):
    rng = random.Random(3005)
    for _ in range(REDACT_RUNS):
        secret = SECRET_MAKERS[shape](rng)
        text = (
            rand_text(rng, 40, PRINTABLE)
            + rng.choice(" \n=:\"'(,")
            + secret
            + rng.choice(" \n\"')/,")
            + rand_text(rng, 40, PRINTABLE)
        )
        assert secret.removeprefix("Bearer ") not in redact(text)


def test_redact_masks_known_secrets_of_length_8_or_more():
    rng = random.Random(3003)
    for _ in range(REDACT_RUNS):
        secrets = [rand_text(rng, 30, PRINTABLE.strip()) for _ in range(rng.randint(1, 3))]
        secrets = [s for s in secrets if len(s) >= 8]
        text = rand_text(rng, 60, PRINTABLE)
        for s in secrets:
            text = embed(rng, text, s)
        out = redact(text, known_secrets=secrets)
        for s in secrets:
            assert s not in out


def test_redact_leaves_plain_words_unchanged():
    rng = random.Random(3004)
    for _ in range(REDACT_RUNS):
        words = [
            "".join(rng.choices(string.ascii_lowercase, k=rng.randint(1, 12)))
            for _ in range(rng.randint(0, 20))
        ]
        text = " ".join(words)
        assert redact(text) == text


def test_redact_masks_a_hex_sk_key_unless_a_vowel_is_glued_to_it():
    # Known residual (THREAT_MODEL T17): "<vowel>sk-<hex>" reads as a word such as "disk-<hash>".
    rng = random.Random(3008)
    for _ in range(REDACT_RUNS):
        secret = "sk-" + "".join(rng.choices("0123456789abcdef", k=32))
        glue = rng.choice([" ", "\n", "=", ":", '"', "x", "k", "Z", "7", "-", "_", "(", ""])
        assert secret not in redact(rand_text(rng, 30, "bcdfg h") + glue + secret + " tail")


ORDINARY_MAKERS = {
    # a word ending in "sk" (vowel before it) followed by a long single-class run
    "sk-word": lambda rng: (
        rng.choice(["ta", "di", "de", "ri", "ma", "a", "bri", "whi", "hu"])
        + "sk-"
        + "".join(rng.choices(string.ascii_lowercase, k=rng.randint(20, 40)))
    ),
    "sk-word-hex": lambda rng: (
        rng.choice(["task", "disk", "desk"]) + "-" + "".join(rng.choices("0123456789abcdef", k=32))
    ),
    "sk-hyphenated": lambda rng: (
        "sk-"
        + "-".join(
            "".join(rng.choices(string.ascii_lowercase, k=rng.randint(3, 9))) for _ in range(5)
        )
    ),
    "token-count": lambda rng: (
        rng.choice(["max_tokens", "input_tokens", "tokens_used", "token_count", "maxTokens"])
        + rng.choice([": ", "=", " = "])
        + str(rng.randint(10**5, 10**9))
    ),
}


@pytest.mark.parametrize("shape", ORDINARY_MAKERS)
def test_redact_leaves_ordinary_text_that_looks_like_a_secret_alone(shape):
    rng = random.Random(3006)
    for _ in range(REDACT_RUNS):
        words = [
            "".join(rng.choices(string.ascii_lowercase, k=rng.randint(1, 8))) for _ in range(4)
        ]
        ordinary = ORDINARY_MAKERS[shape](rng)
        text = f"{words[0]} {words[1]} {ordinary} {words[2]}\n{words[3]}"
        assert redact(text) == text


def test_redact_masks_a_secret_next_to_ordinary_lookalikes():
    rng = random.Random(3007)
    makers = list(SECRET_MAKERS.values())
    for _ in range(REDACT_RUNS):
        secret = rng.choice(makers)(rng)
        ordinary = rng.choice(list(ORDINARY_MAKERS.values()))(rng)
        parts = [ordinary, f"key={secret}", ordinary]
        out = redact(" ".join(parts))
        assert secret.removeprefix("Bearer ") not in out
        assert out.startswith(ordinary) and out.endswith(ordinary)


# 4. term sheet ---------------------------------------------------------------------------------

TERMSHEET_RUNS = 1500
VALID_SHEET = json.loads(
    TermSheet(
        idea="A function that reverses a string.",
        budget_micros=300_000,
        rounds=(Round(1, 100_000, 1), Round(2, 200_000, 2)),
        checks=(
            CheckSpec("c01", "reverses a word", "test_c01.py", "t1"),
            CheckSpec("c02", "reverses empty", "test_c02.py", "t1"),
        ),
        tasks=(Task("t1", "Write rev.py with reverse(s).", ("rev.py",)),),
    ).to_json()
)


def containers(node: object, out: list) -> list:
    if isinstance(node, dict | list):
        out.append(node)
        for child in node.values() if isinstance(node, dict) else node:
            containers(child, out)
    return out


def mutate_sheet(rng: random.Random) -> str:
    doc = json.loads(json.dumps(VALID_SHEET))
    node = rng.choice(containers(doc, []))
    action = rng.choice(["delete", "add", "swap", "truncate"])
    if action == "truncate":
        text = json.dumps(doc)
        return text[: rng.randint(0, len(text))]
    if isinstance(node, dict) and action == "delete" and node:
        del node[rng.choice(sorted(node))]
    elif isinstance(node, dict) and action == "add":
        node[rand_text(rng, 5) or "x"] = rand_json(rng)
    elif action == "swap":
        slot = rng.choice(sorted(node) if isinstance(node, dict) else range(len(node)))
        node[slot] = rand_json(rng)
    elif isinstance(node, list) and node:
        del node[rng.randrange(len(node))]
    return json.dumps(doc)


def test_termsheet_mutations_load_or_raise_termsheet_error():
    rng = random.Random(4001)
    for _ in range(TERMSHEET_RUNS):
        try:
            sheet = TermSheet.from_json(mutate_sheet(rng))
        except TermSheetError:
            continue
        assert isinstance(sheet, TermSheet)


# 5. firing rule --------------------------------------------------------------------------------

RULE_RUNS = 3000
CHECK_IDS = ["c1", "c2", "c3", "c4", "c5"]
STATUSES = ["done", "continuing", "blocked", "none"]


def rand_record(rng: random.Random, i: int, extra: bool = True) -> SliceRecord:
    ids = CHECK_IDS + (["zz"] if extra else [])
    return SliceRecord(
        slice=i,
        cost_micros=rng.choice([None, 0, rng.randint(0, 10**7)]),
        outcome=rng.choice(list(Outcome)),
        status=rng.choice(STATUSES),
        passing=frozenset(rng.sample(ids, rng.randint(0, len(ids)))),
    )


def test_rule_decide_invariants():
    rng = random.Random(5001)
    for _ in range(RULE_RUNS):
        checks = frozenset(rng.sample(CHECK_IDS, rng.randint(1, len(CHECK_IDS))))
        history = [rand_record(rng, i + 1) for i in range(rng.randint(1, 12))]
        if rng.random() < 0.2:
            last = history[-1]
            history[-1] = SliceRecord(
                last.slice, last.cost_micros, last.outcome, last.status, last.passing | checks
            )
        policy = FiringPolicy(rng.randint(1, 5), rng.randint(1, 8))

        verdict = decide(checks, history, policy)
        json.dumps(verdict.evidence)
        latest = history[-1]
        all_pass = checks <= latest.passing
        infra = latest.outcome in INFRASTRUCTURE
        if all_pass:
            assert verdict.decision is Decision.DONE
        elif infra:
            assert verdict.decision is Decision.RETRY
        if latest.status == "blocked" or infra:
            assert verdict.decision is not Decision.FIRE

        padded = list(history)
        for _ in range(rng.randint(1, 4)):
            filler = SliceRecord(
                0,
                rng.choice([None, rng.randint(0, 10**6)]),
                rng.choice(sorted(INFRASTRUCTURE)),
                rng.choice(STATUSES),
                frozenset(),
            )
            padded.insert(rng.randint(0, len(padded) - 1), filler)
        assert decide(checks, padded, policy).decision is verdict.decision


# 6. money formatting ---------------------------------------------------------------------------

MONEY_RUNS = 5000


def test_usd_round_trips_through_usd_arg():
    rng = random.Random(6001)
    values = [rng.randint(1, 10**9) for _ in range(MONEY_RUNS)] + [1, 10**9, 10**6, 999_999]
    for n in values:
        text = usd(n)
        assert usd_arg(text) == n
        assert "e" not in text.lower()
        assert not text.endswith(".")
        assert "." not in text or not text.endswith("0")


# 7. wilson interval ----------------------------------------------------------------------------

WILSON_RUNS = 5000


def test_wilson_interval_brackets_the_proportion():
    rng = random.Random(7001)
    for _ in range(WILSON_RUNS):
        n = rng.randint(1, 500)
        k = rng.randint(0, n)
        low, high = wilson_interval(k, n)
        assert 0 <= low <= k / n <= high <= 1
        if k == 0:
            assert low == 0
        if k == n:
            assert high == 1


# 8. held-out folder and its approval -----------------------------------------------------------

HELD_OUT_RUNS = 300
H_CODE = "from rev import reverse\n\ndef test_a():\n    assert reverse('ab') == 'ba'\n"


def test_held_out_manifests_load_or_raise_held_out_error(tmp_path):
    rng = random.Random(8001)
    for _ in range(HELD_OUT_RUNS):
        doc = rng.choice([rand_json(rng), {"checks": rand_json(rng)}, {"checks": [rand_json(rng)]}])
        (tmp_path / held_out.MANIFEST).write_text(json.dumps(doc), encoding="utf-8")
        try:
            loaded = held_out.load(tmp_path)
        except held_out.HeldOutError:
            assert held_out.problems(tmp_path)
            continue
        assert all(isinstance(c, held_out.HeldOutCheck) for c in loaded)


def test_changing_any_byte_of_any_held_out_file_voids_an_approval(tmp_path):
    rng = random.Random(8002)
    sheet = TermSheet(
        "Reverse.",
        500_000,
        (Round(1, 500_000, 1),),
        (CheckSpec("c01", "d", "test_c01.py", "t1"),),
        (Task("t1", "Create rev.py.", ("rev.py",)),),
    )
    checks = tmp_path / "checks"
    checks.mkdir()
    (checks / "test_c01.py").write_text(H_CODE)
    folder = tmp_path / "held_out"
    ids = [f"h{n:02d}" for n in range(1, 4)]
    entries = [(held_out.HeldOutCheck(i, held_out.file_name(i), "Reverse."), H_CODE) for i in ids]
    held_out.write(folder, entries)
    event = Event(
        run="r", round=0, actor="investor", event=EventType.APPROVED,
        data={"hashes": content_hashes(sheet, checks), "held_out_hashes": held_out.hashes(folder)},
    )  # fmt: skip
    require_approval([event], sheet, checks, folder)
    for _ in range(HELD_OUT_RUNS):
        target = folder / rng.choice([held_out.MANIFEST, *(held_out.file_name(i) for i in ids)])
        original = target.read_bytes()
        at, bit = rng.randrange(len(original)), 1 << rng.randrange(8)
        target.write_bytes(original[:at] + bytes([original[at] ^ bit]) + original[at + 1 :])
        with pytest.raises(NotApprovedError):
            require_approval([event], sheet, checks, folder)
        target.write_bytes(original)
        require_approval([event], sheet, checks, folder)
