"""Mutation-test one module with mutmut against only the tests that exercise it.

    uv run python scripts/mutate.py errors            # run
    uv run python scripts/mutate.py errors --results  # list survivors afterwards

Why a wrapper: mutmut's own stats pass runs the whole suite (about 5000 tests, 23 minutes) and the
config file cannot vary per run, so the focused test files are passed through PYTEST_ADDOPTS.
"""

import os
import subprocess
import sys

# module key -> (mutmut name glob, focused test files)
TARGETS: dict[str, tuple[str, list[str]]] = {
    "errors": ("boss.errors.*", ["test_errors", "test_errors_malformed"]),
    "rule": ("boss.rule.*", ["test_rule"]),
    "budget": ("boss.budget.*", ["test_budget"]),
    "gate": (
        "boss.gate.*",
        ["test_gate", "test_gate_edges", "test_gate_forgery", "test_gate_tree"],
    ),
    "ledger": (
        "boss.ledger.*",
        [
            "test_ledger",
            "test_ledger_chain",
            "test_ledger_edges",
            "test_ledger_repair",
            "test_ledger_anchor",
            "test_signing",
        ],
    ),
    "signing": ("boss.signing.*", ["test_signing", "test_ledger_anchor"]),
    "firm": ("boss.firm.*", ["test_firm", "test_firm_held_out", "test_firm_simulation"]),
    "judge": ("boss.roles.judge.*", ["test_roles_judge", "test_calibration_set"]),
    "table": ("boss.bench.table.*", ["test_bench_table", "test_bench_table_edges"]),
    "kpi": ("boss.bench.kpi.*", ["test_bench_kpi", "test_bench_infra_exclusion"]),
    "paired": ("boss.bench.paired.*", ["test_bench_paired"]),
}


def main(argv: list[str]) -> int:
    if not argv or argv[0] not in TARGETS:
        print(f"usage: mutate.py {{{'|'.join(TARGETS)}}} [--results]", file=sys.stderr)
        return 2
    glob, files = TARGETS[argv[0]]
    env = {**os.environ, "PYTEST_ADDOPTS": " ".join(f"tests/{f}.py" for f in files)}
    cmd = ["mutmut", "results"] if "--results" in argv else ["mutmut", "run", glob]
    return subprocess.call(["uv", "run", *cmd], env=env)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
