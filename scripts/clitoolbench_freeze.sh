#!/bin/sh
# Owner-run, once: freeze CLI-Tool-Bench's Python tasks inside Docker (see clitoolbench_freeze.py).
#   scripts/clitoolbench_freeze.sh <bench-checkout> <out-dir> [--task owner/repo ...]
# The checkout is mounted read-only; only <out-dir> is writable. The container needs the network
# (git clone + pip install of each oracle) and is removed when it exits.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
bench=$(cd "$1" && pwd)
mkdir -p "$2"
out=$(cd "$2" && pwd)
shift 2
docker build -q -t antstreet-clitoolbench-freeze -f "$here/clitoolbench_freeze.Dockerfile" "$here"
docker run --rm -v "$bench:/bench:ro" -v "$out:/out" antstreet-clitoolbench-freeze \
    /bench /out --chown "$(id -u):$(id -g)" "$@"
