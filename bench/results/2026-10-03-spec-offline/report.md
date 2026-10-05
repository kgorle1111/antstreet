# Offline evaluation of the spec layer

Criteria fixed before the run (`CRITERIA.md`, sha256 0ffd531a415a2378) and `SPLITTER` v1:
- O1 pass: all properties hold on every idea and its stripped copy; at most 40 sentences in at least 95% of ideas
- O2: proposer top-1 agreement at least 70%, else hand labels only
- O3 recall pass: at least 60% of the 15 known-omission cells have a flagged rule that is their failing behaviour
- O3 burden pass: median flags per draft at most 4
- O4 pass: kill-rate gap at least 25 points, with at least 40 triples on each side
- O5: reported only

## O1 the splitter

- 59 ideas; property failures: 0; sentences <= 40 in 56/59 (94.9%): **FAIL**
- rules per idea: min 12, median 24, max 34; scored median 20; coarse (one rule per group): jsonpointer, semver, wildcard
- numbering stripped: median rules 22 against 24 (reported, not gated)

## O2 the lexical proposer against the hand labels

- top-1 agreement 74/128 = 58% (criterion 70%): hand labels only
  - bigdecimal: 4/7
  - calc: 5/8
  - csvline: 5/7
  - duration: 3/8
  - intervals: 3/8
  - jsonpointer: 6/8
  - justify: 6/7
  - linediff: 2/8
  - lrucache: 6/7
  - matrixops: 5/8
  - roman: 2/8
  - semver: 4/8
  - slugify: 5/6
  - tokenbucket: 1/7
  - toposort: 4/8
  - wildcard: 7/8
  - workdays: 6/7

## O3 the free verifier on the known omissions

- recall 12/15 = 80% (criterion 60%): **PASS**
- burden: median 3 flagged rules per draft over 169 drafts (criterion <= 4): **PASS**
- chance baseline (added after the first run, not a criterion): flagging the same number of rules at random would hit 11.0 of 15 cells; the cells' own flag counts have median 6

| cell | failing hidden checks | flagged | hit | missing anchor types |
|---|---|---|---|---|
| bigdecimal rep1 | compare | R09, R10, R12, R15, R16, R17, R19, R20 | - | - |
| bigdecimal rep2 | invalid_input | R09, R10, R12, R15, R17, R19 | R09, R10, R12 | enum_item, non_ascii |
| calc rep1 | associativity, malformed_tokens | R04, R05, R07, R11, R13, R20, R21, R23, R24, R25, R26 | R04, R07, R11, R24, R26 | enum_item, exception, magnitude, non_ascii |
| calc rep2 | associativity, malformed_tokens | R04, R07, R13, R19, R20, R23, R24, R25, R26 | R04, R07, R24, R26 | enum_item, exception, non_ascii |
| calc rep3 | malformed_tokens | R04, R05, R21, R23, R24, R26 | R04, R24, R26 | enum_item, exception, non_ascii |
| duration rep1 | parse_negative | R08, R12, R22, R27 | - | - |
| duration rep2 | parse_decimals, parse_negative | R08, R11, R12, R14, R17, R22, R27 | R12, R14 | enum_item, non_ascii |
| duration rep3 | parse_decimals | R08, R12, R13, R17, R22, R27 | R12, R13 | enum_item, literal, non_ascii |
| jsonpointer rep2 | list_indexes, set_value_errors, set_value_isolation | R03, R07 | R07 | non_ascii |
| jsonpointer rep3 | list_indexes, set_value_errors | R03, R07 | R07 | non_ascii |
| semver rep1 | parse_invalid_input, sort_versions | R02, R03, R04, R05, R06, R07, R08, R10, R12 | R03, R05, R08 | enum_item, exception, non_ascii |
| semver rep3 | parse_invalid_input | R02, R03, R04, R05, R06, R07, R08, R12 | R03, R05, R08 | exception, non_ascii |
| tokenbucket rep1 | basic | R10, R11, R16 | R11 | type |
| tokenbucket rep3 | basic | R10, R11, R16 | R11 | type |
| toposort rep2 | dependency_only_nodes | R12, R17, R21 | - | - |

Precision of a flag by the type of the missing anchor, in these cells (added after the first run; a flag is right when its rule is a rule of a failing hidden check). Base rate: 61/273 = 22% of scored rules are such rules.

| missing anchor | right / flags |
|---|---|
| enum_item | 11/39 = 28% |
| exception | 5/5 = 100% |
| literal | 1/22 = 5% |
| magnitude | 1/1 = 100% |
| non_ascii | 15/21 = 71% |
| type | 2/7 = 29% |

Flags per draft by group (median, drafts):
- drafts-single: 4, 17
- drafts-single-think0: 3.5, 16
- final3: 3, 51
- heldout3: 3, 51
- pilot: 4, 17
- rerun1: 4, 17

## O4 does an anchor predict a kill?

- drafts scored 169; hand mutants in play 42
- all anchors present: 539/605 = 89% [86%-91%]
- an anchor missing: 296/350 = 85% [80%-88%]
- gap 4.5 points (criterion >= 25, >= 40 per side): **FAIL**

Kill rate when a rule has a missing anchor of this type:
- enum_item: 58/59 = 98% [91%-100%]
- exception: 4/4 = 100% [51%-100%]
- literal: 201/242 = 83% [78%-87%]
- magnitude: 13/21 = 62% [41%-79%]
- non_ascii: 10/10 = 100% [72%-100%]
- type: 12/16 = 75% [51%-90%]

## O4b failing products as the mutants (added after the first run; no criterion)

- 49 saved products that failed exactly one hidden check; each is run against the drafts of its task except the draft it was built against
- all anchors present: 43/261 = 16% [12%-21%]
- an anchor missing: 4/567 = 1% [0%-2%]
- gap 15.8 points

Kill rate when a rule has a missing anchor of this type:
- enum_item: 3/217 = 1% [0%-4%]
- exception: 0/107 = 0% [0%-3%]
- literal: 1/16 = 6% [1%-28%]
- magnitude: 0/5 = 0% [0%-43%]
- non_ascii: 1/287 = 0% [0%-2%]
- type: 0/75 = 0% [0%-5%]

## O5 noise (reported only)

- 598 flags over all drafts; 266 (44%) on a rule whose hidden checks every saved product of the task passed; 10 on a rule no hidden check was labelled with
