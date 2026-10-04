# What multi-agent systems are measured to be good at

Collected 2026-10-03 to decide what this project should build and measure. Each row names its
source and date; "vendor" means an internal evaluation with no public control. Nothing here is a
result of this project: our own figures are in `bench/results/`, and what we will test is fixed in
[PREREG.md](PREREG.md) before any run.

## The short answer

Measured multi-agent gains are narrow: breadth-parallel, read-heavy work; a clean-context reviewer
or checker; and a cheap executor with a strong advisor, on cost. Debate, personas, swarms and
parallel writers mostly vanish once a single agent gets the same compute. Our own result (firm 69%
against single 63% at 2.4x cost, 17 small tasks) fits that literature.

## Evidence for

| Claim | Number | Task type | Source, date | Status |
|---|---|---|---|---|
| Parallel breadth | +90.2% over one agent; about 15x the tokens, and tokens alone explain 80% of the variance | Research and search | Anthropic, multi-agent research system, 2025-06-13 | Vendor, not compute-matched; the same post calls coding a poor fit |
| Centralised vs independent agents | Centralised +80.9% on finance tasks; every variant -39% to -70% on planning; independent agents amplify errors 17.2x, centralised 4.4x | Finance, planning, web, tools | Google Research, arXiv 2512.08296, 2026-01 | Controlled; no coding task confirmed |
| Separate evaluator | Solo build had a broken core feature; with an evaluator it worked, at 22x the cost; agents "confidently praise" their own work | Full app build, one example | Anthropic, harness design for long-running apps, 2026-03-24 | Anecdote |
| Clean-context code review | Substantive review comments on 16% to 54% of pull requests; under 1% of findings marked wrong | Pull-request review | Anthropic code review (secondary source), 2026-03-09 | Vendor |
| Cheap executor + strong advisor | +2.7 points on SWE-bench Multilingual at -11.9% cost per task (5 trials, 300 problems) | Coding | Anthropic, the advisor strategy, 2026-04-09 | Vendor, but cost-controlled: the best evidence for code |
| Context management | Context editing cut tokens 84% | Agentic search | Anthropic, context management, 2025 | Vendor; a single agent gets this too |

## Evidence against

- At equal thinking tokens, single agents match or beat five multi-agent architectures on multi-hop
  QA; gains are "better explained by unaccounted computation" (Tran and Kiela, arXiv 2604.02460,
  2026-04).
- Automated multi-agent designs against self-consistency sampling: about 10x the cost for no gain;
  SWE-bench Lite 57.1% (sampling) against 56.0% (best multi-agent) (arXiv 2606.13003, 2026-06).
- Debate's gains are mostly majority voting (Choi et al., NeurIPS 2025, arXiv 2508.17536); mixing
  models loses to sampling the best one (Self-MoA, arXiv 2502.00674, 2025-02).
- Multi-agent failure taxonomy: 41-86.7% task failure across 7 frameworks; 41.8% design, 36.9%
  inter-agent misalignment, 21.3% verification (MAST, arXiv 2503.13657, 2025-03). No single-agent
  baseline, so it shows how they fail, not that they lose.
- Parallel writers make conflicting implicit decisions (Cognition, 2025-06); by 2026-04 the same
  team endorses read-only subagents, clean-context review and a stronger "smart friend" model.
- More agent-written tests did not change SWE-bench resolution (arXiv 2602.07900, 2026-02);
  self-correction without external feedback does not help (Huang et al., ICLR 2024); persona
  prompts give no reliable gain (Zheng et al., EMNLP 2024).
- Coordination overhead: 3-10x tokens (Anthropic, 2026-01-23).

## When a multi-agent design should win

- The work splits into independent parts with frozen interfaces.
- The work is broader than one context.
- Checking is cheaper than building, and an undetected error is expensive.
- The visible/hidden gap grows about 28 points per 10x of code size (SpecBench, arXiv 2605.21384,
  2026-05): our small single-module tasks are where an independent checker helps least.

It should lose on tightly coupled code, shared state, sequential reasoning, and tasks one agent
already solves.

## How serious comparisons are run

- A compute-matched single agent: loop it, retry it or sample it to the same dollars or tokens.
- A bigger single model at the multi-agent system's budget.
- Graders the systems never see; judges blind to which system produced an output.
- pass^k (every one of k runs) as well as pass@k; wall-clock and cost reported together.
- Paired, task-clustered intervals: with 17 tasks, an unpaired 6-point gap would need about 950
  trials per arm to detect (Miller, arXiv 2411.00640).
