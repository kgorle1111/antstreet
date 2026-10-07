# Gate sandbox

The gate (`src/boss/gate.py`) runs worker- and boss-written code with pytest. `src/boss/sandbox.py`
wraps that one process in an OS sandbox where the platform has one. It narrows what the code can
do to the machine. It does not make the verdict unforgeable (T12, only partly closed by the gate's plugin) and it is not a container.
Threat rows: T05, T12, T13, T14, T39 in `THREAT_MODEL.md`.

## Turning it on, off, or making it mandatory

- `BOSS_GATE_SANDBOX=auto` (default): sandbox when a tool works, otherwise run unsandboxed.
- `BOSS_GATE_SANDBOX=require`: no working tool means a `GateError` naming the tool and the fix.
- `BOSS_GATE_SANDBOX=off`: never sandbox.
- `run_gate(..., sandbox=SandboxMode.X)` beats the variable. The variable is read in one place, at
  the start of `run_gate`; any other value is a `GateError`.
- `boss doctor` prints a `gate sandbox` line: the tool found, or a warning with the fix. It only
  fails under `require`, or for a bad value.
- Every `CheckResult` has `sandboxed`. `False` means unsandboxed, whether by `off` or by `auto`
  finding no tool. `boss report` does not show it yet.
- Benchmark runs (`boss.bench`) go through `run_gate` too, so `auto` sandboxes them.

## What is denied (macOS, verified by tests in `tests/test_gate_sandbox.py`)

- All network: TCP and UDP to local listeners, opening a listener, Unix sockets, DNS.
- Every write outside the check's own run folder (`boss_gate_*` temp dir): create, overwrite,
  append, delete, rename, mkdir, symlink, truncate, chmod. Applies to child processes too.
- Every read outside the allowlist below, including the real workspace (the gate reads its copy),
  the user's home and `/etc/hosts`. Directory listings too.
- All Mach services except the user-name lookup: no keychain daemon, clipboard, `open`,
  `osascript`, `launchctl`.
- Signals to any process outside the sandbox (the gate's own process included).
- Applying a second sandbox from inside (`sandbox_apply: Operation not permitted`), so a check
  cannot re-sandbox itself into something looser.

## What is allowed, and why

Found by running the gate's exact command under `(deny default)` and adding rules until an honest
check passed, then removing each rule to see whether anything noticed (mutation table below).

| Rule | Why |
|---|---|
| `process-fork`, `process-exec` | pytest, `subprocess`, multiprocessing. Any program may run, confined. |
| `signal (target same-sandbox)` | A check killing its own child (`Popen.kill`). |
| `sysctl-read`, `file-read-metadata` | Python and libc startup. `stat` therefore works on any path. |
| `ipc-posix-sem` | `multiprocessing` locks and pools. |
| `mach-lookup com.apple.system.opendirectoryd.libinfo` | `getpass.getuser()` and `pwd` fall back to the user database. |
| read `/` (the directory itself) | Without it the process aborts at launch (exit 134, no message). |
| read the run folder, `sys.prefix`, `sys.base_prefix` (resolved) | The check and its workspace copy; the virtualenv with pytest; the interpreter and stdlib. May sit under the home directory. |
| read `/private/var/db/timezone` | Without it the local time zone silently becomes UTC (`datetime.now().astimezone()`). |
| read `/usr/share/zoneinfo.default` | The built-in time zone copy. `/usr/share/zoneinfo` resolves here on a Mac that has not downloaded a time zone update (a fresh CI runner), and `zoneinfo.ZoneInfo(...)` fails without it. |
| read `/usr/share/locale` | Without it `locale.getpreferredencoding()` returns `utf-8` instead of `UTF-8`. |
| read and write `/dev/null` | pytest opens `os.devnull`. |
| write the run folder | Workspace copy, check, report, proof file, `HOME`, `TMPDIR`. The report is here, hence T12. |

Not needed, so not allowed: `/usr`, `/bin`, `/System`, `/Library`, `/private/etc`,
`/dev/urandom` (Python uses `getentropy`). System binaries still run without a read grant
(`/usr/bin/true`, `/bin/echo`, `/bin/sh` all ran).

Paths are never spliced into profile text. On macOS they are `sandbox-exec -D KEY=path` parameters
used as `(subpath (param "KEY"))`; on Linux they are `bwrap` arguments. The profile text depends
only on the count of readable paths, so a directory named `"))(allow default)((` grants that
directory and nothing else (`test_a_hostile_directory_name_grants_that_directory_and_nothing_else`;
a profile that interpolated the path fails it on quote, backslash and injection names).

## What it does not protect against

- **A forged verdict aimed at the gate's plugin (T12).** Rewriting the report, exiting 0 or patching
  pytest no longer passes (`test_a_report_rewritten_from_inside_the_sandbox_is_not_a_pass`). Code that
  reads the per-run nonce from the plugin's module in its own process still can
  (`test_accepted_risk_code_aimed_at_the_gate_still_forges_a_pass_inside_the_sandbox`).
- **The run folder itself.** The check file, `pytest.ini`, the workspace copy and `HOME` are
  writable by the code under test.
- **Existence probing.** `stat` works everywhere (pinned by `test_the_names_of_files_are_still_visible_to_stat`).
- **Resource use.** No CPU, memory, disk or process-count limit (T37).
- **A detached child (T05).** `start_new_session=True` escapes the timeout's process-group kill,
  sandboxed or not. It stays confined. On Linux the pid namespace should end with it (below).
- **The worker CLI.** Only the gate's pytest process is sandboxed (T18, T19).
- **Any machine without a working tool** under `auto`: unsandboxed, and only `CheckResult.sandboxed`
  and `boss doctor` say so (T39).
- **Honest checks that need what the profile withholds:** localhost servers, sockets, `git`
  (the shim reads the Xcode tools under `/Library`: `xcrun: error: unable to load libxcrun`),
  subprocesses that read files outside the allowlist. They fail as worker failures.
  `sandbox=OFF` is the escape hatch.
- **`sandbox-exec` is deprecated** by Apple. It works on macOS 26.6.2; the probe in `detect()`
  reports it unavailable if it stops working.

## Comparisons: a product value cannot decide its own check (T12)

An object whose `__eq__` always returns True passes `assert reverse("ab") == "ba"` without a right
answer, and needs no knowledge of the gate. The gate's plugin wraps pytest's assertion rewrite:
after pytest rewrites the check file, every `== != < <= > >= in not in` in it (in an assert or not,
in a comprehension, in a helper) has each operand passed through `_guard`.

- **Honest values are compared as Python compares them.** Exact `None bool int float complex str
  bytes bytearray range type Decimal` and the `datetime` types, a `Fraction` of two ints, and
  `list tuple dict set frozenset deque OrderedDict defaultdict Counter` and dict views whose contents
  are honest, walked with the base type's own iterator. A subclass of `list tuple dict set frozenset`
  (a namedtuple) counts if it keeps every comparison method of its base. Nothing is made stricter:
  `1 == 1.0`, `True == 1` and `Counter("aab") == {"a": 2, "b": 1}` still hold. A check that wants an
  exact type says so (`type(x) is int`).
- **`pytest.approx` objects count only if the check file built them** (the plugin wraps
  `pytest.approx` and records objects created from a frame in the check file). One the product
  returns can hold a value that equals everything, or an infinite tolerance.
- **Anything else is wrapped.** The wrapper is never equal to an honest value and cannot be ordered
  against one (`TypeError`). Two wrapped values compare as the product says, and `x in product_obj`
  asks the product's `__contains__`, so `Poly(1) == Poly(1)` and `"ab" in trie` keep working.
- **Fail closed:** a collected test whose module was not rewritten with the guard (a pytest that
  stopped calling `rewrite_asserts`) is never counted as passed, so the gate says FAILED.

Covered: `==`, `!=` (via the reflected and direct paths), `in`/`not in` against an honest container,
`sorted(x) == [...]` (elements are walked), chained comparisons, a value hidden inside a list or tuple,
comparisons outside an assert. Not covered:

- Comparisons between two product objects, and `in` on a product container: the product decides.
  A check that compares a product object to a plain value (`Money(5) == 5`) now fails; compare a
  plain projection (`int(m) == 5`, `m.cents == 500`).
- An exact-type scalar subclass: an `IntEnum` member is not equal to `3` under the guard.
- `unittest` assert methods (`self.assertEqual`): the comparison happens inside `unittest`, not in
  the check file. Boss-drafted and benchmark checks use `assert`.
- Bare truthiness (`assert f(x)`), `len(x)` (a product object can report any length), and what a
  product's `__str__`, `__iter__` or `__hash__` returns before a plain comparison sees it. These
  give the product nothing an honest-looking return value would not.
- Whole-tree runs (`gate.run_tree`, imported benchmark suites): no plugin, no guard, no proof.
- Code aimed at the plugin: replacing `_guard` or `pytest.approx` in its own process (the
  `accepted_risk` tests stand for this class).

## Plan: a verdict read from outside the process (T12, not built)

Every in-process control above shares one limit: the nonce, the monitoring and the guard live in the
process that runs the product, so code written against this gate can reach them. Reading
pytest's outcomes from a parent over a pipe does not help: the child writes the pipe and can lie.
The parent has to evaluate the expectations itself, which means product code and check code must
run in different processes.

The smallest design that does that:

1. **Checker process (trusted):** pytest, the check file, the plugin and the nonce. It never
   imports product code. A meta-path import hook turns `import rev` (any module found in the
   workspace) into a proxy module.
2. **Product server (sandboxed as today, no nonce, no write access to the proof path):** imports
   the product and answers requests over a pair of pipes: get an attribute, call, set an attribute,
   iterate, compare, contains. Length-prefixed JSON, never pickle (unpickling runs code in the
   checker).
3. **Values cross by value only if `_honest`** (the same rules as the guard), as tagged JSON.
   Anything else becomes a handle; comparing or testing membership on handles is a request to the
   server, so the product still decides between its own objects, exactly as the guard allows today.
4. **Exceptions:** a product exception class becomes a proxy class in the checker, with its name,
   the nearest builtin exception as base and one class per remote class, so
   `pytest.raises(ValueError)` and `pytest.raises(InsufficientFunds)` both work.
5. **Callbacks:** a function the check passes into the product (18 of 457 hidden check files contain
   a lambda) becomes a handle the server calls back into, so the protocol is re-entrant.

What it would change for checks (why it is a separate, breaking PR): an argument the product
mutates in place is a copy, so the check does not see the change; `a is b` on two returns of one
product object needs handle caching; monkeypatching a product module in the check no longer reaches
the code (no hidden check does today); every product call becomes a round trip
(`test_from_roman_inverts_to_roman_for_every_number` makes 8,000). Size: a checker-side proxy and
import hook, a product server, a codec with a fuzz test, `gate._run_one` launching two processes
under the sandbox, and a rerun of every forgery test and every benchmark task: on the order of
1,000 to 1,500 lines over 8 to 10 files, plus the behaviour change above.

What would stay forgeable: the product's answers about its own objects (as now), a bug in the
proxy or codec (the new boundary), and anything the check file or pytest itself does wrong (T14).
Until it is built, the two `accepted_risk` forge tests stay pinned and T12 stays `accepted`.

## Probes, 2026-09-30

Machine: macOS 26.6.2 (build 25G83), Darwin 25.6.0, arm64. Python 3.12.13 (uv-managed, under the
home directory, virtualenv in the worktree). No `bwrap` on this machine.

- `/usr/bin/sandbox-exec -p '<profile>' python -I -B -m pytest ...` runs the gate's exact command.
  It `exec`s in place, so the gate's process-group kill still reaches the check and its children.
- A profile with `(deny default)` needed the rules in the table above and nothing else, for a
  probe check that used asyncio, threads, thread and process pools (spawn), sqlite3, ssl, zoneinfo,
  tempfile, subprocess (own child and `/bin/echo`), `os.urandom`, `getpass`, `locale`, and killing
  its own child.
- Profile pitfalls: without `(allow file-read-metadata)` or without a read grant on `/` the process
  aborts before Python starts (exit 134 or -6, no message, no denial found in `log show`); `(trace ...)` in
  a profile wrote no trace file here.
- Rejected without running it: `(allow default)` plus denies. By construction it leaves every Mach
  service reachable, and the unsandboxed run shows what that reaches (keychain daemon answered,
  clipboard read 149 bytes, `open` and `osascript` ran, `launchctl list` printed 540 lines). A
  list of services to deny is never complete; a list to allow is.
- Tried and abandoned: scoping `file-read-metadata` to the path ancestors instead of everywhere.
  `execvp` of the virtualenv's Python failed with the first ancestor list I tried (probably
  firmlinks such as `/System/Volumes/Data`; not investigated); left as a documented leak.
- `sandbox-exec -D KEY=value` with `(subpath (param "KEY"))` handled spaces, quotes, parentheses,
  a newline, a backslash, `;`, non-ASCII and an injected `"))(allow default)((` name.
- A nested `sandbox-exec` from inside the profile fails with `sandbox_apply: Operation not
  permitted`. A nested one from an `(allow default)` parent works.
- Unsandboxed vs sandboxed, same attack scripts, unsandboxed first: TCP bind ok / denied; Unix
  socket bind ok / denied; DNS ok / `gaierror`; write into the home directory ok / denied; list
  `~/.ssh` and `~/.claude` ok / denied; `/etc/hosts` ok / denied; `open -a Finder` rc 0 / rc 1;
  `osascript` rc 0 / rc 1; `pbpaste` rc 0 / rc 1; keychain lookup "item could not be found" /
  a different error (the daemon unreachable); `launchctl list` 540 lines / none; `git --version`
  ok / xcrun error; `os.kill(parent, 0)` ok / denied.

### Overhead

Same one-test check through `run_gate`, 10 runs each, alternating, two rounds:

| | mean | median |
|---|---|---|
| OFF | 0.235 s, 0.233 s | 0.234 s, 0.234 s |
| sandboxed | 0.242 s, 0.242 s | 0.243 s, 0.242 s |

About +9 ms (4%) per check. `detect()` adds one probe (about 0.2 s) per process, cached.

## Linux (`bwrap`): runs and is required in CI

Written without a Linux host; CI now runs it, with `BOSS_GATE_SANDBOX=require`, on every Linux test job. The argv
`sandbox.bwrap_argv` builds, in order:

```
bwrap --die-with-parent --unshare-net --unshare-pid --unshare-ipc
  --ro-bind / /  --dev /dev  --proc /proc
  --tmpfs /home  --tmpfs /root  --tmpfs /tmp  --tmpfs /run
  --ro-bind <each readable path not inside a secret> <same>   # interpreter and virtualenv
  --tmpfs <project>/.boss  (or --ro-bind /dev/null <file>)   # secrets, see below
  --ro-bind <each readable path inside a secret> <same>      # e.g. the checks folder, re-exposed
  --bind <run folder> <same>                 # the only writable path
  -- <command>
```

### What stays readable on Linux

The root is bound read-only, so everything outside `/home`, `/root`, `/tmp` and `/run` is readable
by a check: a project under `/srv`, `/opt` or `/work` would expose `<project>/.boss/` (the investor
key, the ledger, the run store). `gate.secret_paths` therefore names the `.boss` folder above the
workspace or checks it is given, plus `BOSS_AUDIT_HOME` when set, and `bwrap_argv` masks each one
(`--tmpfs` for a folder) after the four tmpfs mounts and after every readable bind that is not
inside a secret, then re-binds the readable paths that are (the check's own folder under `.boss`).
bwrap applies mounts in argv order, so a readable path that contains a secret (an ancestor) is
bound before the mask and cannot re-expose it, and one inside a mask re-exposes only itself. A `.boss` folder inside the workspace or an exported tree is never copied into the check's
workspace (`gate._COPY_IGNORE`), so the writable copy holds no key. A key kept anywhere else is not hidden; the upgrade path is an allowlist root. macOS needs no
mask: its profile denies every read that is not listed. Tests: `tests/test_sandbox_secrets.py`.

### How CI runs it

`.github/workflows/ci.yml`, ubuntu job only:

1. `sudo apt-get install -y bubblewrap`.
2. Ubuntu 24.04 sets `kernel.apparmor_restrict_unprivileged_userns=1`, under which bwrap fails with
   `setting up uid map: Permission denied`. If the restriction is on, the step loads an AppArmor
   profile that grants `userns` to `/usr/bin/bwrap` and nothing else (the restriction stays on for
   every other program). The step ends with a bwrap run of its own so the log shows bwrap's error;
   the gate only reports "unavailable". If that profile ever fails to load, the one-line fallback is
   `sudo sysctl -w kernel.apparmor_restrict_unprivileged_userns=0`, which lifts the restriction for
   the whole machine: acceptable on a throwaway hosted runner, not on a persistent one.
3. The test step runs with `BOSS_GATE_SANDBOX=require`. A bwrap that cannot start now makes the
   test modules fail at collection with `SandboxUnavailable` and its fix (`tests/sandbox_support.py`),
   where before the sandbox tests skipped and the gate ran unsandboxed under `auto`. macOS keeps
   `auto`.

### The four guarantees, side by side

| Guarantee | macOS profile | bwrap argv |
|---|---|---|
| No network | `(deny default)`, no `network*` | `--unshare-net`: a new network namespace with only a loopback. A check can open a listener or send a datagram on that private loopback; nothing outside can reach it and it reaches nothing outside. Not identical to macOS, where both are denied |
| Writes only in the run folder | no `file-write*` except the folder and `/dev/null` | `--ro-bind / /` (recursive: submounts are remounted read-only too) and one `--bind` of the run folder. `/tmp`, `/home`, `/root`, `/run` and `/dev` are fresh tmpfs mounts a check can write to, but they exist only inside the sandbox and vanish with it |
| Reads only the allowlist | the run folder, the interpreter and virtualenv, time zone and locale data | weaker: the whole root is readable except `/home`, `/root`, `/tmp`, `/run`. `/etc`, `/usr`, `/var`, `/opt`, `/mnt` and `/srv` can be read. Parents of the re-exposed paths exist as empty directories holding only the allowed path. Tightening this is B50 |
| Signals only inside | `signal (target same-sandbox)` | `--unshare-pid` with a fresh `--proc`: processes outside have no pid in the sandbox. A kill of the sandbox's init (the group kill at a timeout) ends the whole namespace, so a detached child should die with it (T05, if the first Linux run confirms it) |

Also: `--unshare-ipc` gives the check its own SysV IPC namespace (the seatbelt profile denies SysV
shared memory by default); `--die-with-parent` ends the sandbox if the gate dies.

Differences a test can see (`tests/test_gate_sandbox.py`, branches on `bwrap`): a write outside the
run folder fails with `FileNotFoundError` instead of `PermissionError`, because the directory is
hidden, not denied; a UDP send does not raise; opening a listener is not refused; the neighbours of
the interpreter can be listed; a detached child does not survive the timeout.

### Choices

- `/home`, `/root`, `/tmp` and `/run` (Docker and agent sockets live there) are emptied.
- `--unshare-pid` with a fresh `--proc`: without it `/proc/<pid>/environ` of the caller would leak.
- No `--new-session`: the gate already starts the check with `start_new_session=True`, and
  `bwrap`'s `setsid()` fails for a process that already leads a session (from its source, not run).
  Add it if `bwrap` is ever used without `start_new_session`.
- Not added, for want of a Linux host to try them on: `--unshare-user` with `--disable-userns` (the
  Linux counterpart of "cannot re-sandbox from inside"; it needs the nested namespace to work under
  the AppArmor profile), `--unshare-cgroup` (the host's cgroup path is visible, nothing more) and
  an allowlist root (B50).

### What the Linux CI run exercises

These were unverified when the argv was written. The Linux jobs run with `BOSS_GATE_SANDBOX=require`,
so a bwrap that cannot start fails the build:

- That the AppArmor profile loads and lets bwrap start on the current `ubuntu-latest`.
- That the probe command (`python -I -B -c "import pytest"`) starts under the full argv: the order
  of `--tmpfs /home` and the `--ro-bind` of a virtualenv or interpreter under `/home`, and
  `--tmpfs /root` (it needs `/root` to exist, because the root is read-only).
- That `HOME` and `TMPDIR` under `/tmp` survive the `--tmpfs /tmp` then `--bind` order.
- That `multiprocessing` (POSIX semaphores on `--dev`'s `/dev/shm`) and `getpass.getuser()` work.
- That the loopback is up inside `--unshare-net` (the UDP and listener branches assume it is).
- That a hung check and its children, detached ones included, die with the group kill.
- To check by hand on Linux: `BOSS_GATE_SANDBOX=require uv run pytest tests/test_gate_sandbox.py`.
  Tests marked `mac_only` skip; the rest must pass or the argv gets fixed.

## Do the tests fail without each rule?

Each rule was weakened in turn (`(allow network*)`, `(allow file-write*)`, `(allow file-read*)`,
dropping a grant, and so on) and the sandbox tests run. Failures in every case; for grants whose
loss breaks the profile so badly that `detect()` calls the tool unusable, the real tests skip and
`test_a_seatbelt_tool_that_works_means_our_profile_lets_python_start` fails instead.

| Weakened | Tests that failed |
|---|---|
| `(allow network*)` | TCP, UDP, Unix socket, listener |
| all writes allowed | 23: every write op, worker code, validation-time check code |
| all reads allowed | 17+: secrets, listing, workspace, prefix neighbours, child process |
| drop timezone read | ordinary code, time zone |
| drop locale read | ordinary code |
| drop semaphores | ordinary code (process pool) |
| drop same-sandbox signal | ordinary code (child kill) |
| any signal allowed | signal to the gate's process |
| drop user lookup | ordinary code (`getpass`) |
| any Mach lookup allowed | keychain, clipboard, `open`, `osascript` |
| drop fork, `/dev/null`, unresolved run folder | honest checks fail |
| drop exec, metadata, root read, interpreter prefixes | profile unusable: the guard test fails |
| gate never wraps, ignores the mode, or reports `sandboxed=False` | 27 to 32 tests each |
| paths interpolated into profile text | hostile-name tests (quote, backslash, injection) |
