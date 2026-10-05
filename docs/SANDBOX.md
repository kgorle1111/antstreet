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

## Linux (`bwrap`): built, first run is CI

Written without a Linux host: none of this had been executed when it was written. The argv
`sandbox.bwrap_argv` builds, in order:

```
bwrap --die-with-parent --unshare-net --unshare-pid --unshare-ipc
  --ro-bind / /  --dev /dev  --proc /proc
  --tmpfs /home  --tmpfs /root  --tmpfs /tmp  --tmpfs /run
  --tmpfs <project>/.boss  (or --ro-bind /dev/null <file>)   # secrets, see below
  --ro-bind <each readable path> <same>      # interpreter and virtualenv, re-exposed under the tmpfs
  --bind <run folder> <same>                 # the only writable path
  -- <command>
```

### What stays readable on Linux

The root is bound read-only, so everything outside `/home`, `/root`, `/tmp` and `/run` is readable
by a check: a project under `/srv`, `/opt` or `/work` would expose `<project>/.boss/` (the investor
key, the ledger, the run store). `gate.secret_paths` therefore names the `.boss` folder above the
workspace or checks it is given, plus `BOSS_AUDIT_HOME` when set, and `bwrap_argv` masks each one
(`--tmpfs` for a folder) after the four tmpfs mounts and before the binds. bwrap applies mounts in
argv order, so the binds re-expose only the check's own folder, even when it lies under a masked
path. A `.boss` folder inside the workspace or an exported tree is never copied into the check's
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

### Not verified until the first Linux CI run

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
