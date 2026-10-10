# 2026-10-10-spec-gaps

SG1 from [`bench/PREREG.md`](../../PREREG.md#sg1-spec-gap-questions-surface-rules-the-drafted-checks-miss):
after the boss drafts its checks, does the `--questions` call (`spec_gaps_v1.md`, at most 5 yes/no
questions) ask about a rule the idea states that the drafted checks would miss? Live runs on
2026-10-10, Haiku, one run per case, clean environment. The evidence is the two question files in
this folder (`known_questions.json`, `heldout_questions.json`); the model's output in them was read as
data. No model call was made for this write-up.

## Answer

**Not shown.** Held-out hand-checked recall is 4 of 10 [17%, 69%]; the bar is 5 of 10. The regex
scorer says 2 of 10. Known-set recall (5 of 10 by hand) is not evidence of generalisation, as
registered.

A first draft of this write-up counted a fifth held-out hit, `intervals-touching-merge`, and called the
bar met. Review showed that its question ("Does merge work with negative integers like
merge([(-2, 0), (0, 2)])?") is answered yes or no, and either answer leaves open whether that pair
merges, so under the registered rule ("its answer decides the rule's behaviour") it is a miss. The
draft was corrected before merging; see that row below.

Read plainly: the questions asked about some held-out rules, about 4 in 10 here, and the interval does
not separate that from 50%. `--questions` stays opt-in and makes no claim to find the gaps that matter.

## Method

- Cases: `bench/spec_gaps/cases.json` (known: 10 rules the boss's checks missed in the false-pass
  audit; the prompt names their gap classes) and `bench/spec_gaps/heldout.json` (held out: 10 rules
  quoted from `bench/tasks/*/idea.md`, chosen before any run, in ordering, tie-break, parsing and date
  classes the prompt does not name).
- Per case: draft checks as `boss fund` does (call 1), then ask the questions (call 2).
  `python -m antstreet.bench.spec_gaps --cases <set> live --yes-spend --out <file>`.
- Regex score: the `match` patterns in the case files. **Hand check** (decides): a question surfaces a
  rule when its answer decides the rule's behaviour for some input the rule covers (PREREG SG1). Each
  case is judged only on its own questions.

## Results

| Set | Regex recall | Hand recall [95% Wilson] | Well formed (<=5, all yes/no) | Spent |
|---|---|---|---|---|
| Known | 4/10 | **5/10 [24%, 76%]** | 10/10 [72%, 100%] | $1.7227 (measured) |
| Held out | 2/10 | **4/10 [17%, 69%]** | 10/10 [72%, 100%] | at least $1.7315 |

Well formed is vacuous for `csvline-whitespace-kept`: it has 0 questions (the call produced none), and
0 questions is "at most 5, all yes/no". Without it, held-out well-formedness is 9/9 and that case is
a miss.

### Known set (hand check)

| Case | Regex | Hand | Surfacing question, or why none |
|---|---|---|---|
| bigdecimal-nonascii | yes | yes | "Should add('٣', '1') raise ValueError for a non-ASCII digit?" |
| bigdecimal-compare-scale | no | no | Asks about non-ASCII add, `multiply('5','1.')`, `add('007','003')`; none about `compare` across decimal places. |
| calc-nonascii | no | no | Unary-minus depth, `1 / -2`, `(1)(2)`, non-string arguments; none about non-ASCII digits. |
| calc-long-chain | yes | yes | "Must evaluate() handle 2000 additions without hitting Python's recursion limit?" |
| duration-minus-space | no | yes | "Should parse_duration('- 1h') raise ValueError?" (whitespace after the minus) |
| jsonpointer-no-sharing | yes | **no** | Closest: "Should resolve return the exact object reference from the document, not a copy?" That is rule 8 (`resolve` returns the object itself), not rule 9 (`set_value` shares no dict or list with the input). Every question is about `resolve`. |
| semver-nonascii | yes | yes | "Should parse('1.2.3-ü') raise ValueError?" |
| semver-sort-invalid | no | no | Asks about `parse`, `compare`; none about `sort_versions` raising. |
| tokenbucket-float | no | no | Asks about default `cost`, `allow(100.0)`, `allow(0.3)`; none about the type `available()` returns. |
| toposort-generators | no | yes | "Should toposort({'a': [], 'b': (x for x in ['a'])}) return ['a', 'b']?" (a one-shot iterator as a value) |

Disagreements (3): `duration-minus-space` and `toposort-generators` regex miss, hand hit;
`jsonpointer-no-sharing` regex hit, hand miss (the regex matched "copy"/"exact object" in a question
about a different function).

### Held-out set (hand check)

| Case | Regex | Hand | Surfacing question, or why none |
|---|---|---|---|
| moneysplit-largest-fraction | no | yes | "Should split_by_ratio(13, [1, 1, 1]) return [5, 4, 4]?" (equal fractions, earlier first) and "Should split_by_ratio(10, [1, 0, 2]) return [3, 0, 7]?" (the leftover cent goes to the largest fraction). |
| multisort-missing-last | yes | yes | "...place the record missing \"s\" after those with \"s\" values, within its dept group?" |
| intervals-touching-merge | no | **no** | "Does merge work with negative integers like merge([(-2, 0), (0, 2)])?" uses a touching pair, but a yes or a no says nothing about whether it merges into `[(-2, 2)]`, so its answer does not decide the rule (first draft: "yes, borderline"; corrected in review). Other questions: input not mutated, `subtract` with empty `b`, `total_length` of overlapping intervals; none touching. |
| lrucache-read-no-extend | no | no | The only question is about `keys()` returning a new list. |
| cronnext-dom-or-dow | no | yes | "Should `0 0 31 2 1` fire on Mondays in February even though February has no 31st?" (day-of-month and day-of-week are ORed) |
| urlquery-plus-space | yes | yes | "Does parse_query('a%20b=1&a+b=2') return {'a b': ['1', '2']}?" (`+` becomes a space; says nothing about `%2B`) |
| httpheaders-get-joins | no | no | "...get('A') return '1 2'" is about a folded continuation line, not `get` joining repeated headers. |
| iniparse-no-inline-comment | no | no | Duplicate keys, `[section]extra`, empty input; none about `a = b ; c`. |
| workdays-months-not-chained | no | no | `add_months(date(2024, 1, 31), 1)` gives Feb 29 under chaining and direct computation alike; it cannot tell them apart. The rest are about business days. |
| csvline-whitespace-kept | no | no | No questions. |

Disagreements (2): `moneysplit-largest-fraction` and `cronnext-dom-or-dow` regex miss, hand hit. No regex hit that the hand check rejects. The regex is
lexical, so it misses a rule asked about through an example (`0 0 31 2 1`, `[1, 1, 1]`) rather than in
words: it under-counts here, and over-counted once on the known set.

## Cost

$1.7227 measured on the known set; $1.7315 on the held-out set, **at least**: one call reported no cost
(`live` flags this and adds nothing for it), so the true figure is higher by an unknown amount.
Together at least $3.4542, above the "about $2-3 in all" in the PREREG. Whether it stayed under the
owner's $4 stop is not known: the uncosted call would have to exceed $0.55 to cross it, against about
$0.17 for a whole case, but its cost was not recorded.

The PREREG estimate of about $0.30 a set was 6 times low. Not because it left out the draft call
(`estimate()` counted both calls) but because its output guesses (2,000 and 2,500 tokens a call) ignored
that Haiku's output includes thinking: the draft alone is about $0.10 a case (as in
`2026-09-30-drafts-and-audit`), the questions about $0.07. `estimate()` now uses 20,000 and 14,000
output-equivalent tokens and gives $1.78 for a 10-case set, with a test that fails if it drifts back
below $1.00.

## Limits

- 10 cases a set. The interval at 4/10 is [17%, 69%] and contains the 50% bar: "not shown" is not
  "shown useless", and one more hit would have met the bar.
- The person who set the rules also hand-checked them; a second checker was not used. One case,
  `intervals-touching-merge`, was scored a hit in the first draft and a miss after review.
- One model (Haiku), one run per case. The same case could surface or not on a second run; run-to-run
  variation was not measured.
- A hit is "a question touches the rule", not "the investor would have answered it correctly" or "the
  checks then catch a broken implementation". Nothing here measures downstream delivery.
- The held-out set was chosen without reading model output, but the choice of "ordering, tie-break,
  parsing, date" rules is mine; other classes may do better or worse.
- Each case's checks are a fresh draft, not the draft of the original false-pass cell.

What would change the conclusion: a second held-out set of 10-20 fresh rules scored by two
checkers, with held-out recall at or above 50% on the combined 20-30 would move it to "useful beyond known
gaps". A combined held-out recall below 40% would make "not shown" firmer.
