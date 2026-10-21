#!/bin/sh
# Owner-run, once: freeze CLI-Tool-Bench's Python tasks inside Docker (see clitoolbench_freeze.py).
#
#   scripts/clitoolbench_freeze.sh [--dry-run] --image-digest sha256:<64 hex> \
#       <bench-checkout> <out-dir> [--task owner/repo ...] [--cases-per-task N]
#
# BEFORE RUNNING: quit local services (Command Center :4173, Forge :8765, Concierge :4310) and
# anything bound on localhost or your LAN. Phase install has the network; the host aliases are
# nulled (--add-host host.docker.internal:127.0.0.1, gateway.docker.internal likewise), but on
# Docker Desktop the host may still be reachable by its gateway IP.
# kn: no egress allowlist; full fix is a proxy that allows only github.com, pypi.org and
# files.pythonhosted.org, on an --internal network that phase install joins instead of the default.
#
# Three containers from one image, all as your own uid with every capability dropped, no new
# privileges, 512 processes, 4 GB, 2 CPUs and a wall-clock limit (CLITB_PHASE_LIMIT_S, default
# 21600 s each; macOS has no `timeout`, so a background watchdog runs `docker stop`, which
# --stop-timeout turns into a kill after 10 s):
#   install (network on): loads each task's start.py and runs its install_oracle (git clone + pip
#     install, so setup.py and build backends run WITH network), into a named volume.
#   run (--network none): generates the cases and runs every oracle offline; writes only into the
#     volume, never to your disk.
#   export (--network none, volume read-only, only our own code runs): copies only regular files
#     named index.json, cases.json, spec.md, skipped.json, each bounded, into <out-dir>.
# The checkout is read-only in every phase. --dry-run prints the docker commands instead of
# running them (the tests check them).
set -eu

dry=0
digest=""
while [ $# -gt 0 ]; do
    case "$1" in
        --dry-run) dry=1; shift ;;
        --image-digest) digest=${2:-}; shift 2 ;;
        *) break ;;
    esac
done
if [ $# -lt 2 ]; then
    echo "usage: $0 [--dry-run] --image-digest sha256:<hex> <bench-checkout> <out-dir> [args]" >&2
    exit 2
fi
if ! printf '%s\n' "$digest" | grep -Eq '^sha256:[0-9a-f]{64}$'; then
    echo "error: pass the digest of the base image you pulled, e.g." >&2
    echo "  docker pull python:3.12-bookworm" >&2
    echo "  docker inspect --format '{{index .RepoDigests 0}}' python:3.12-bookworm" >&2
    echo "then --image-digest sha256:<the 64 hex after the @>" >&2
    exit 2
fi

here=$(cd "$(dirname "$0")" && pwd -P)
repo=$(cd "$here/.." && pwd -P)
bench=$(cd "$1" && pwd -P)
home=$(cd "${HOME:-/nonexistent}" 2>/dev/null && pwd -P || echo /nonexistent)

# The real path of $1: its deepest existing ancestor resolved with `pwd -P` (every symlink
# followed), plus the parts that do not exist yet.
resolve() {
    p=$1
    rest=""
    while [ ! -e "$p" ] && [ ! -L "$p" ]; do
        rest="/$(basename "$p")$rest"
        p=$(dirname "$p")
    done
    printf '%s%s\n' "$(cd "$p" && pwd -P)" "$rest"
}

check_out() {
    case "$1/" in
        "$repo"/*) echo "error: $1 is inside the repository; use a folder outside it" >&2; exit 2 ;;
        "$home"/Library/*) echo "error: $1 is under ~/Library; use a plain folder" >&2; exit 2 ;;
        "$home"/*)
            case "/${1#"$home"/}/" in
                */.*) echo "error: $1 is under a dot folder of \$HOME; use a plain folder" >&2
                      exit 2 ;;
            esac ;;
    esac
    if [ -e "$1" ] && [ -n "$(ls -A "$1")" ]; then
        echo "error: $1 is not empty; the freeze writes only into an empty folder" >&2
        exit 2
    fi
}

case "$2" in /*) out=$2 ;; *) out=$(pwd -P)/$2 ;; esac
out=$(resolve "$out")
check_out "$out"
shift 2

echo "Before the freeze: quit local services (Command Center :4173, Forge :8765," \
    "Concierge :4310) and anything bound on localhost or your LAN. Phase install has the" \
    "network and runs third-party setup code." >&2

limit=${CLITB_PHASE_LIMIT_S:-21600}
image="antstreet-clitoolbench-freeze:$(printf '%s' "$digest" | cut -c8-19)"
stamp="$(date +%Y%m%d%H%M%S)-$$"
volume="antstreet-clitb-work-$stamp"
user="$(id -u):$(id -g)"

run() {
    if [ "$dry" = 1 ]; then
        printf '%s\n' "$*"
    else
        "$@"
    fi
}

# `docker run` with a wall-clock limit: a background watchdog stops the named container.
limited() {
    name=$1
    shift
    if [ "$dry" = 1 ]; then
        printf '%s\n' "$*"
        return 0
    fi
    "$@" &
    pid=$!
    (sleep "$limit" && docker stop --time 10 "$name" >/dev/null 2>&1) &
    dog=$!
    status=0
    wait "$pid" || status=$?
    kill "$dog" 2>/dev/null || true
    return "$status"
}

hardening="--rm --user $user --cap-drop ALL --security-opt no-new-privileges --pids-limit 512"
hardening="$hardening --memory 4g --cpus 2 --stop-timeout 10"
hardening="$hardening --add-host host.docker.internal:127.0.0.1"
hardening="$hardening --add-host gateway.docker.internal:127.0.0.1"

run docker build --build-arg "BASE_DIGEST=$digest" -t "$image" \
    -f "$here/clitoolbench_freeze.Dockerfile" "$here"
run docker volume create "$volume"
# shellcheck disable=SC2086  # $hardening is a list of flags on purpose
limited "clitb-install-$stamp" docker run --name "clitb-install-$stamp" $hardening \
    -v "$bench:/bench:ro" -v "$volume:/clitb-work" \
    "$image" --phase install --image-digest "$digest" /bench "$@"
# shellcheck disable=SC2086
limited "clitb-run-$stamp" docker run --name "clitb-run-$stamp" --network none $hardening \
    -v "$bench:/bench:ro" -v "$volume:/clitb-work" \
    "$image" --phase run --image-digest "$digest" --out /clitb-work/out /bench "$@"
if [ "$dry" = 0 ]; then
    mkdir -p "$out"
    out=$(resolve "$out")  # made now: check the real folder again before anything is written
    check_out "$out"
fi
# shellcheck disable=SC2086
limited "clitb-export-$stamp" docker run --name "clitb-export-$stamp" --network none $hardening \
    -v "$volume:/clitb-work:ro" -v "$out:/out" \
    "$image" --phase export --from /clitb-work/out --out /out
echo "done; the scratch volume can go when you are sure: docker volume rm $volume" >&2
