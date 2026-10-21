"""Freeze CLI-Tool-Bench's Python tasks into deterministic offline cases. Owner-run, in Docker only.

    scripts/clitoolbench_freeze.sh <bench-checkout> <out-dir> [--task owner/repo ...]

CLI-Tool-Bench grades a product by cloning the live oracle repo, pip-installing it and fuzzing both
with unseeded `random`. That cannot be re-run offline or reproduced, so this script runs once,
inside the container built from scripts/clitoolbench_freeze.Dockerfile (it refuses to run unless
CLITOOLBENCH_IN_CONTAINER=1, which only that image sets), and records what the oracle did.

Per task (`owner/repo` from PYTHON_TASKS, or each --task):

1. Imports the task's own fuzzer, run_differential_test/repo/<owner>/<repo>/start.py, with a stub
   in place of DiffTestEngine (the engine and its Docker client are never run). Its adapter is
   reused as written: `install_oracle` gets a stand-in container whose `exec_run` runs the command
   here, inside this container, and `generate_test_cases` makes the cases. Reusing the fuzzer, not
   re-implementing it, keeps each task's command patterns and fixtures exactly as published.
2. Installs the oracle that way (git clone of its live repo + pip install, as start.py says)
   into a venv of its own (stdlib `venv`, so oracles never share packages or a script name) and
   records the clone's origin URL, HEAD commit sha, the first line of its LICENSE file, the
   console scripts it installed and any other distributions it pulled in. A failed install, or no
   single git clone found, skips the task (`skipped.json` with the reason).
3. Seeds `random` with SEED (0, recorded) and generates the cases; generates them a second time
   from the same seed and flags the task if the two lists differ.
4. Takes distinct cases one category at a time (round robin) until exactly CASES_PER_TASK
   (N = 50, recorded; --cases-per-task) are frozen; fewer possible skips the task. For each: a
   fresh test-data folder (the adapter's `test_data_dir`, the working folder of the run)
   holding its fixture files, a fresh HOME, the oracle's clone restored to its installed
   state, then `prep_script` and `command` with `/bin/sh -c` (30 s each). Records the exit
   code, stdout (ANSI codes stripped, as BaseRepoAdapter.sanitize_stdout does) and the
   filesystem delta under the test-data folder (path -> ADD/MOD with sha256 and the content,
   or DEL). Every case runs twice; if the two runs differ the oracle is flaky and the WHOLE
   task is skipped. A case is dropped, with its reason, when it touches the oracle's install
   folder (the product has none), sets a variable the replay owns, times out twice, or prints
   more than 64 KiB.
   Third-party code: the oracle's other distributions are recorded, and the task is skipped only
   when its stdout holds text a third-party package wrote (AUDIT_HOOK), with that evidence.
5. Writes <out>/<owner>__<repo>/cases.json (format FORMAT, read by
   antstreet.bench.imported.convert_clitoolbench) and spec.md (the task's agent_prompt.txt), and
   <out>/index.json: seed, N, Python version, frozen tasks, skipped ones with their reasons.

Paths are stored with placeholders: the test-data folder as {TEST_DATA}, /tmp as {TMP}, in
commands, stdout and file contents alike, so the replay can run in any temporary folder.
Standard library only; it imports nothing from antstreet. Matching is EM/FM only: there is no
language-model judge anywhere (bench/STANDARDS.md S7).
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.util
import json
import os
import platform
import random
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tarfile
import types
from collections.abc import Sequence
from io import BytesIO
from pathlib import Path
from typing import Any, NamedTuple

CONTAINER_ENV = "CLITOOLBENCH_IN_CONTAINER"
FORMAT = "antstreet-clitoolbench-frozen/1"
SEED = 0
CASE_TIMEOUT_S = 30
INSTALL_TIMEOUT_S = 900
MAX_STDOUT_CHARS = 64 * 1024
MAX_FILE_BYTES = 1024 * 1024  # a file the oracle writes; its content is kept for the replay check
CASES_PER_TASK = 50  # the fixed N: every frozen task has exactly this many cases (recorded)
# Third-party writers that only print the text they are given (the oracle's own words).
PASS_THROUGH = frozenset({("click", "echo"), ("click", "secho")})
# Put on PYTHONPATH as sitecustomize.py for every oracle run. Records, once per (file, function),
# the innermost non-stdlib frame that wrote to sys.stdout, so text a third-party package wrote can
# be told from text the oracle wrote. Text the oracle formats with a library and then prints
# itself (a table built by a formatter) is attributed to the oracle: this is a lower bound.
AUDIT_HOOK = """import json, os, sys, sysconfig

_log = os.environ.get("CLITB_STDOUT_AUDIT")
if _log:
    _skip = tuple(p for p in (sysconfig.get_paths().get(k) for k in ("stdlib", "platstdlib")) if p)
    _seen = set()

    class _Audit:
        def __init__(self, inner):
            self._inner = inner

        def write(self, text):
            frame = sys._getframe(1)
            while frame is not None and (
                frame.f_code.co_filename.startswith(_skip + ("<",))
                or frame.f_code.co_filename == __file__
            ):
                frame = frame.f_back
            if frame is not None:
                where = (frame.f_code.co_filename, frame.f_code.co_name)
                if where not in _seen:
                    _seen.add(where)
                    with open(_log, "a", encoding="utf-8") as out:
                        out.write(json.dumps([*where, str(text)[:200]]) + "\\n")
            return self._inner.write(text)

        def __getattr__(self, name):
            return getattr(self._inner, name)

    sys.stdout = _Audit(sys.stdout)
"""
# Same text as antstreet.bench.imported.ANSI_PATTERN (a test holds them equal).
ANSI_PATTERN = r"\x1b\[[0-?]*[ -/]*[@-~]"
ANSI = re.compile(ANSI_PATTERN)
TEST_DATA, TMP = "{TEST_DATA}", "{TMP}"
# The replay sets these; a case that sets one cannot be replayed as recorded. Same set as
# antstreet.bench.imported._HARNESS_ENV (a test holds them equal).
HARNESS_ENV = frozenset(
    {
        "PATH",
        "HOME",
        "TMPDIR",
        "PYTHONPATH",
        "PYTHONHOME",
        "PYTHONSTARTUP",
        "PYTHONDONTWRITEBYTECODE",
        "PYTHONIOENCODING",
        "LANG",
        "LC_ALL",
        "CLITB_PYTHON",
    }
)
_SHELL_CHARS = set("|&;<>()$`\\\n*?[]{}~!#")
# The 34 Python tasks of docs/TASK_CATALOG.md (read 2026-10-21).
PYTHON_TASKS = (
    "cyberxuan-XBX/gscc",
    "hoangsonww/SQL-Mongo-Query-Converter",
    "austinyu/ujson5",
    "crux-ecosystem/mol-lang",
    "UiPath/graphtty",
    "seojoonkim/prompt-guard",
    "mosquito/debx",
    "toon-format/toon-python",
    "andrewx-bu/mp4analyzer",
    "MehdiSaraeian/todo-bridge",
    "parneetsingh022/pygha",
    "smat-dev/jinni",
    "Aman-s12345/python-code-graph",
    "AmirhosseinHonardoust/Market-Cycle-Gene-Forecasting-Engine",
    "tcsenpai/obsipub",
    "ShahzaibAhmad05/gitree",
    "assalas/pcb-designer-ai-agent",
    "Riley702/enhanced_benchmark_tool",
    "timf34/JSONDetective",
    "Cosm00/qlog",
    "swyxio/claude-compaction-viewer",
    "Riley702/outlier-detection-tool",
    "tawandakembo/code-collator",
    "jaunruh/jmux",
    "panispani/sanitext",
    "horiacristescu/nub",
    "pinin4fjords/nf-metro",
    "xaviviro/python-toon",
    "pengzhendong/compute-wer",
    "AZidan/codemap",
    "kennethreitz-archive/uvenv",
    "uladkaminski/pyparseit",
    "simonw/files-to-prompt",
    "rayokota/jsonata-python",
)


class Skip(Exception):
    """This task cannot be frozen; the message says why and goes in skipped.json, with any
    evidence behind it."""

    def __init__(self, reason: str, evidence: list[dict[str, str]] | None = None) -> None:
        super().__init__(reason)
        self.evidence = evidence or []


class ExecResult(NamedTuple):
    exit_code: int
    output: bytes


class LocalContainer:
    """Stands in for the docker-py container an adapter's install_oracle expects.

    The freeze already runs inside a disposable container, so a command runs here. As docker-py
    does, a string is split with shlex and run without a shell; stderr is merged into the output.
    """

    id = "local"

    def __init__(self, cwd: Path, env: dict[str, str]) -> None:
        self.cwd, self.env = cwd, env

    def exec_run(
        self,
        cmd: str | Sequence[str],
        workdir: str | None = None,
        environment: Any = None,
        **_: Any,
    ) -> ExecResult:
        argv = shlex.split(cmd) if isinstance(cmd, str) else [str(c) for c in cmd]
        env = dict(self.env)
        if isinstance(environment, dict):
            env.update({str(k): str(v) for k, v in environment.items()})
        elif isinstance(environment, list):
            env.update(item.split("=", 1) for item in environment if "=" in item)
        try:
            done = subprocess.run(
                argv,
                cwd=workdir or self.cwd,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=INSTALL_TIMEOUT_S,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return ExecResult(127, str(exc).encode())
        return ExecResult(done.returncode, done.stdout)

    def put_archive(self, path: str, data: bytes) -> bool:
        with tarfile.open(fileobj=BytesIO(data)) as archive:
            archive.extractall(path, filter="data")
        return True


def _stub_engine() -> None:
    module = types.ModuleType("DiffTestEngine")

    class DiffTestEngine:
        def __init__(self, *args: object, **kwargs: object) -> None:
            raise RuntimeError("the freeze never runs the upstream DiffTestEngine")

    module.DiffTestEngine = DiffTestEngine  # type: ignore[attr-defined]
    sys.modules["DiffTestEngine"] = module


def _load_adapter(start: Path, n: int) -> Any:
    spec = importlib.util.spec_from_file_location(f"clitoolbench_start_{n}", start)
    if spec is None or spec.loader is None:
        raise Skip(f"cannot import {start}")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        raise Skip(f"importing start.py failed: {_last_line(exc)}") from exc
    found = [
        obj
        for obj in vars(module).values()
        if isinstance(obj, type)
        and obj.__module__ == module.__name__
        and any(base.__name__ == "BaseRepoAdapter" for base in obj.__mro__[1:])
    ]
    if len(found) != 1:
        raise Skip(f"start.py defines {len(found)} adapters, expected exactly one")
    return found[0]()


def _last_line(exc: BaseException) -> str:
    text = f"{type(exc).__name__}: {exc}".strip()
    return text.splitlines()[-1][:500] if text else type(exc).__name__


def _custom_sanitizer(adapter: Any) -> bool:
    for cls in type(adapter).__mro__:
        if cls.__name__ == "BaseRepoAdapter":
            return False
        if "sanitize_stdout" in vars(cls):
            return True
    return False


# Run by the task's venv interpreter: what is installed there, not in the freeze's own.
_DISTS_SOURCE = """import importlib.metadata as m, json, sys
from pathlib import Path
want, out = set(sys.argv[1:]), {}
for d in m.distributions():
    name = f"{d.metadata['Name']}=={d.version}"
    if not want:
        out[name] = sorted(e.name for e in d.entry_points if e.group == "console_scripts")
    elif name in want:
        for f in d.files or []:
            if str(f).endswith(".py"):
                out[str(Path(str(d.locate_file(f))).resolve())] = name
print(json.dumps(out))
"""


def _venv_query(python: Path, *deps: str) -> dict[str, Any]:
    """No deps: 'name==version' -> console scripts of each distribution in the venv. With deps:
    resolved .py file -> 'name==version' for those distributions."""
    done = subprocess.run(
        [str(python), "-I", "-c", _DISTS_SOURCE, *deps],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    if done.returncode != 0:
        raise Skip(f"cannot list the task venv's distributions: {done.stderr.strip()[-300:]}")
    result: dict[str, Any] = json.loads(done.stdout)
    return result


def _make_venv(venv: Path, with_pip: bool) -> Path:
    """A venv of this interpreter for one task, so oracles never share site-packages or a
    console-script name. pip comes from the interpreter's bundled ensurepip wheel."""
    argv = [sys.executable, "-I", "-m", "venv", str(venv)]
    done = subprocess.run(
        argv if with_pip else [*argv, "--without-pip"],
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    if done.returncode != 0:
        raise Skip(f"cannot make the task venv: {done.stderr.strip()[-300:]}")
    return venv / "bin"


def _listing(folder: Path) -> set[str]:
    return {p.name for p in folder.iterdir()} if folder.is_dir() else set()


def _find_clone(roots: Sequence[Path]) -> Path:
    clones: set[Path] = set()
    for root in roots:
        if not root.is_dir():
            continue
        for candidate in (root, *sorted(p for p in root.iterdir() if p.is_dir())):
            if (candidate / ".git").exists():
                clones.add(candidate.resolve())
    if len(clones) != 1:
        raise Skip(f"found {len(clones)} git clones of the oracle, expected exactly one")
    return clones.pop()


def _git(clone: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", "-C", str(clone), *args], capture_output=True, text=True, check=False
    )
    if done.returncode != 0:
        raise Skip(f"git {' '.join(args)} failed in the oracle clone: {done.stderr.strip()}")
    return done.stdout.strip()


def _licence(clone: Path) -> str:
    for path in sorted(clone.iterdir()):
        if path.is_file() and path.name.upper().startswith(("LICENSE", "LICENCE", "COPYING")):
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                if line.strip():
                    return line.strip()[:200]
    return "NOT FOUND (no LICENSE file at the oracle's root)"


def _reset(folder: Path) -> None:
    if folder.exists():
        shutil.rmtree(folder)
    folder.mkdir(parents=True)


def _normalise_text(text: str, td: Path) -> str:
    return text.replace(str(td), TEST_DATA).replace("/tmp", TMP)


def _normalise(data: bytes, td: Path) -> bytes:
    return data.replace(str(td).encode(), TEST_DATA.encode()).replace(b"/tmp", TMP.encode())


def _state(root: Path, td: Path, ignored: frozenset[str]) -> dict[str, str]:
    found: dict[str, str] = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in ignored)
        for name in filenames:
            path = Path(dirpath, name)
            if path.is_file() and not path.is_symlink():
                digest = hashlib.sha256(_normalise(path.read_bytes(), td)).hexdigest()
                found[path.relative_to(root).as_posix()] = digest
    return found


def _delta(before: dict[str, str], after: dict[str, str]) -> dict[str, dict[str, str | None]]:
    delta: dict[str, dict[str, str | None]] = {}
    for rel in sorted(before.keys() | after.keys()):
        if rel not in after:
            delta[rel] = {"type": "DEL", "sha256": None}
        elif rel not in before:
            delta[rel] = {"type": "ADD", "sha256": after[rel]}
        elif before[rel] != after[rel]:
            delta[rel] = {"type": "MOD", "sha256": after[rel]}
    return delta


def _sh(script: str, cwd: Path, env: dict[str, str]) -> tuple[int, bytes] | None:
    """Exit code and stdout, or None on a timeout (the whole process group is killed)."""
    proc = subprocess.Popen(
        ["/bin/sh", "-c", script],
        cwd=cwd,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    try:
        out, _ = proc.communicate(timeout=CASE_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        proc.communicate()
        return None
    # A shell killed by a signal: report it the way sh would, 128 + the signal.
    code = proc.returncode
    return (code if code >= 0 else 128 - code), out


def _fixtures(mount_files: object, td: Path) -> dict[str, Any]:
    if not isinstance(mount_files, dict):
        raise ValueError("mount_files is not a dict")
    fixtures: dict[str, Any] = {}
    for raw, content in sorted(mount_files.items()):
        rel = str(raw)
        if rel.startswith(str(td) + "/"):
            rel = rel[len(str(td)) + 1 :]
        parts = rel.split("/")
        if rel.startswith("/") or "\\" in rel or any(p in ("", ".", "..") for p in parts):
            raise ValueError(f"fixture {raw!r} is outside the test-data folder")
        if isinstance(content, bytes):
            fixtures[rel] = {"base64": base64.b64encode(content).decode()}
        elif isinstance(content, str):
            fixtures[rel] = content
        else:
            raise ValueError(f"fixture {raw!r} is neither text nor bytes")
    return fixtures


def _write_fixtures(td: Path, fixtures: dict[str, Any]) -> None:
    for rel, content in fixtures.items():
        path = td / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, dict):
            path.write_bytes(base64.b64decode(content["base64"]))
        else:
            path.write_bytes(content.encode("utf-8", "surrogatepass"))


def _argv(command: str) -> list[str] | None:
    if _SHELL_CHARS & set(command):
        return None
    try:
        return shlex.split(command)
    except ValueError:
        return None


class Oracle(NamedTuple):
    clone: Path
    snapshot: Path
    env: dict[str, str]
    td: Path
    home: Path
    ignored: frozenset[str]
    audit: Path  # the stdout audit log of the current run (see AUDIT_HOOK)


def _run_case(oracle: Oracle, case: Any, fixtures: dict[str, Any]) -> Any:
    """(exit code, stdout, fs delta, audit records) of one run, or a string saying why it cannot
    be frozen. ADD/MOD entries carry the new content (base64, paths as placeholders) so that the
    converter's replay check can write them back."""
    _reset(oracle.td)
    _reset(oracle.home)
    shutil.rmtree(oracle.clone)
    shutil.copytree(oracle.snapshot, oracle.clone, symlinks=True)
    oracle.audit.unlink(missing_ok=True)
    _write_fixtures(oracle.td, fixtures)
    env = {**oracle.env, "HOME": str(oracle.home)}
    env.update({str(k): str(v) for k, v in dict(case.env_vars or {}).items()})
    env.update(PYTHONPATH=str(oracle.audit.parent), CLITB_STDOUT_AUDIT=str(oracle.audit))
    if case.prep_script and _sh(case.prep_script, oracle.td, env) is None:
        return f"prep_script took more than {CASE_TIMEOUT_S}s"
    before = _state(oracle.td, oracle.td, oracle.ignored)
    oracle.audit.unlink(missing_ok=True)  # only the command's own writes count
    done = _sh(case.command, oracle.td, env)
    if done is None:
        return f"the oracle took more than {CASE_TIMEOUT_S}s"
    delta: dict[str, dict[str, Any]] = dict(
        _delta(before, _state(oracle.td, oracle.td, oracle.ignored))
    )
    for rel, change in delta.items():
        if change["type"] != "DEL":
            data = _normalise((oracle.td / rel).read_bytes(), oracle.td)
            if len(data) > MAX_FILE_BYTES:
                return f"the oracle wrote {rel}, larger than {MAX_FILE_BYTES} bytes"
            delta[rel] = {**change, "content": base64.b64encode(data).decode()}
    stdout = ANSI.sub("", _normalise(done[1], oracle.td).decode("utf-8", "replace"))
    if len(stdout) > MAX_STDOUT_CHARS:
        return f"stdout is longer than {MAX_STDOUT_CHARS} characters"
    return done[0], stdout, delta, _audit_records(oracle.audit)


def _audit_records(path: Path) -> list[list[str]]:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    records = []
    for line in lines:
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if (
            isinstance(record, list)
            and len(record) == 3
            and all(isinstance(x, str) for x in record)
        ):
            records.append(record)
    return records


def dep_evidence(records: list[list[str]], dep_files: dict[str, str]) -> list[dict[str, str]]:
    """Writes to stdout whose innermost non-stdlib caller is a file of a third-party
    distribution the oracle pulled in, minus pass-through writers (click.echo prints the
    oracle's own text). `dep_files`: resolved file path -> 'name==version'."""
    found = []
    for filename, function, sample in records:
        dep = dep_files.get(filename)
        if dep is None:
            try:
                dep = dep_files.get(str(Path(filename).resolve()))
            except OSError:
                dep = None
        if dep is None:
            continue
        if (dep.split("==")[0].lower(), function) in PASS_THROUGH:
            continue
        found.append({"dep": dep, "file": filename, "function": function, "sample": sample})
    return found


def _generate(adapter: Any) -> list[Any]:
    random.seed(SEED)
    try:
        return list(adapter.generate_test_cases())
    except Exception as exc:
        raise Skip(f"the fuzzer failed: {_last_line(exc)}") from exc


def _key(case: Any) -> str:
    fields = [case.command, case.prep_script, case.mount_files, case.env_vars]
    return json.dumps(fields, sort_keys=True, default=repr)


def _round_robin(generated: list[Any]) -> list[Any]:
    """Distinct cases, one category at a time in the order categories first appear, so a cap of
    N cases spreads over every command pattern instead of the first few."""
    queues: dict[str, list[Any]] = {}
    seen: set[str] = set()
    for case in generated:
        key = _key(case)
        if key not in seen:
            seen.add(key)
            queues.setdefault(str(getattr(case, "category", "UNKNOWN")), []).append(case)
    ordered: list[Any] = []
    depth = 0
    while any(depth < len(q) for q in queues.values()):
        ordered += [q[depth] for q in queues.values() if depth < len(q)]
        depth += 1
    return ordered


def freeze_task(
    bench: Path, task: str, work: Path, cases_per_task: int, with_pip: bool, n: int
) -> tuple[dict[str, Any], str]:
    """The cases.json content and the spec of one task. Raises Skip."""
    start = bench / "run_differential_test" / "repo" / task / "start.py"
    prompt = bench / "agent_prompt" / task / "agent_prompt.txt"
    for path in (start, prompt):
        if not path.is_file():
            raise Skip(f"{path.relative_to(bench)} is missing")
    random.seed(SEED)
    adapter = _load_adapter(start, n)
    td = Path(adapter.test_data_dir)
    repo_root = str(getattr(adapter, "repo_root_dir", "/repo")).rstrip("/")
    install = work / "install"
    install.mkdir(parents=True)
    bindir = _make_venv(work / "venv", with_pip)
    env = dict(os.environ)
    env.update(
        PATH=os.pathsep.join([str(bindir), env.get("PATH", "/usr/bin:/bin")]),
        VIRTUAL_ENV=str(work / "venv"),
        HOME=str(work / "home-install"),
        LANG="C.UTF-8",
        LC_ALL="C.UTF-8",
        PYTHONIOENCODING="utf-8",
        PYTHONDONTWRITEBYTECODE="1",
    )
    env.pop(CONTAINER_ENV, None)
    scripts_before, dists_before = _listing(bindir), _venv_query(bindir / "python")
    try:
        adapter.install_oracle(LocalContainer(install, env))
    except Exception as exc:
        raise Skip(f"oracle install failed: {_last_line(exc)}") from exc
    programs = sorted(_listing(bindir) - scripts_before)
    if not programs:
        raise Skip("the oracle installed no console script; the launcher needs one")
    new = {d: s for d, s in _venv_query(bindir / "python").items() if d not in dists_before}
    deps = sorted(d for d, scripts in new.items() if not set(scripts) & set(programs))
    clone = _find_clone([install, Path(repo_root)])
    snapshot = work / "snapshot"
    shutil.copytree(clone, snapshot, symlinks=True)
    oracle_meta = {
        "url": _git(clone, "remote", "get-url", "origin"),
        "commit": _git(clone, "rev-parse", "HEAD"),
        "licence": _licence(clone),
        "python": platform.python_version(),
        "deps": deps,
        "programs": programs,
    }
    flags = ["custom_stdout_sanitizer"] if _custom_sanitizer(adapter) else []
    generated = _generate(adapter)
    if [_key(c) for c in generated] != [_key(c) for c in _generate(adapter)]:
        flags.append("fuzzer_not_reproducible_from_the_seed")
    ignored = frozenset(str(d) for d in getattr(adapter, "workspace_diff_ignore_dir_names", []))
    (work / "audit").mkdir()
    (work / "audit" / "sitecustomize.py").write_text(AUDIT_HOOK)
    oracle = Oracle(clone, snapshot, env, td, work / "home", ignored, work / "audit" / "log")
    dep_files = _venv_query(bindir / "python", *deps) if deps else {}
    cases: list[dict[str, Any]] = []
    dropped: list[dict[str, str]] = []
    evidence: list[dict[str, str]] = []
    for case in _round_robin(generated):
        if len(cases) == cases_per_task:
            break
        category = str(getattr(case, "category", "UNKNOWN"))

        def drop(reason: str, category: str = category) -> None:
            dropped.append({"category": category, "reason": reason})

        env_vars = {str(k): str(v) for k, v in dict(case.env_vars or {}).items()}
        try:
            fixtures = _fixtures(case.mount_files, td)
        except ValueError as exc:
            drop(str(exc))
            continue
        texts = (case.command, case.prep_script or "")
        if any(repo_root + "/" in t or t.endswith(repo_root) for t in texts):
            drop("touches the oracle's install folder, which the product does not have")
            continue
        if HARNESS_ENV & env_vars.keys():
            drop(f"sets {sorted(HARNESS_ENV & env_vars.keys())}, which the replay owns")
            continue
        first, second = _run_case(oracle, case, fixtures), _run_case(oracle, case, fixtures)
        if isinstance(first, str) and first == second:
            drop(first)
            continue
        # The whole task goes: one flaky case means the oracle's behaviour is not a fixed target.
        if first != second:
            raise Skip(f"flaky: two runs of the oracle differed on {category!r}: {case.command!r}")
        evidence += [
            {"case": f"c{len(cases) + 1:04d}", **e} for e in dep_evidence(first[3], dep_files)
        ]
        command = _normalise_text(case.command, td)
        cases.append(
            {
                "id": f"c{len(cases) + 1:04d}",
                "category": category,
                "command": command,
                "argv": _argv(command),
                "stdin": "",
                "env": {k: _normalise_text(v, td) for k, v in env_vars.items()},
                "prep_script": _normalise_text(case.prep_script or "", td),
                "fixtures": fixtures,
                "expected": {"exit_code": first[0], "stdout": first[1], "fs_delta": first[2]},
            }
        )
    if evidence:
        raise Skip(
            "the oracle's stdout includes text written by a third-party package the product "
            f"cannot use ({sorted({e['dep'] for e in evidence})})",
            evidence[:50],
        )
    if len(cases) < cases_per_task:
        raise Skip(f"only {len(cases)} of {cases_per_task} cases could be frozen")
    data = {
        "format": FORMAT,
        "task": task,
        "seed": SEED,
        "cases_per_task": cases_per_task,
        "test_data_dir": str(td),
        "ignore_dirs": sorted(ignored),
        "oracle": oracle_meta,
        "flags": flags,
        "dropped": dropped,
        "cases": cases,
    }
    return data, prompt.read_text(encoding="utf-8", errors="replace")


def _chown(root: Path, owner: str) -> None:
    uid, gid = (int(x) for x in owner.split(":"))
    for dirpath, _, filenames in os.walk(root):
        os.chown(dirpath, uid, gid)
        for name in filenames:
            os.chown(os.path.join(dirpath, name), uid, gid)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("bench", type=Path, help="CLI-Tool-Bench checkout (read only)")
    parser.add_argument("out", type=Path, help="folder to write the frozen tasks into")
    parser.add_argument("--task", action="append", help="owner/repo (default: the 34 Python tasks)")
    parser.add_argument("--cases-per-task", type=int, default=CASES_PER_TASK, help="the fixed N")
    parser.add_argument("--work", type=Path, default=Path("/clitb-work"), help="scratch folder")
    parser.add_argument(
        "--venv-without-pip",
        action="store_true",
        help="tests only: task venvs without pip (a fake oracle installs no package)",
    )
    parser.add_argument("--chown", help="UID:GID to give the output files at the end")
    args = parser.parse_args(argv)
    if os.environ.get(CONTAINER_ENV) != "1":
        print(
            "refusing to run: this installs and runs third-party code, so it runs only inside "
            "its Docker container (scripts/clitoolbench_freeze.sh builds and starts it, and the "
            f"image sets {CONTAINER_ENV}=1)",
            file=sys.stderr,
        )
        return 2
    bench = args.bench.resolve()
    if not (bench / "run_differential_test").is_dir():
        print(f"error: {bench} has no run_differential_test/", file=sys.stderr)
        return 2
    if args.cases_per_task < 1:
        print("error: --cases-per-task must be at least 1", file=sys.stderr)
        return 2
    tasks = args.task or list(PYTHON_TASKS)
    out = args.out
    clashes = [t for t in tasks if (out / t.replace("/", "__")).exists()]
    if clashes:
        print(f"error: already frozen in {out}: {clashes}; remove them first", file=sys.stderr)
        return 2
    out.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(bench / "run_differential_test"))
    _stub_engine()
    frozen: list[str] = []
    skipped: dict[str, str] = {}
    for n, task in enumerate(tasks):
        name = task.replace("/", "__")
        dest = out / name
        work = args.work / name
        if work.exists():
            shutil.rmtree(work)
        try:
            data, spec = freeze_task(
                bench, task, work, args.cases_per_task, not args.venv_without_pip, n
            )
        except Skip as exc:
            skipped[task] = str(exc)
            dest.mkdir()
            (dest / "skipped.json").write_text(
                json.dumps({"task": task, "reason": str(exc), "evidence": exc.evidence}, indent=2)
                + "\n"
            )
            print(f"skipped {task}: {exc}", file=sys.stderr)
            continue
        dest.mkdir()
        (dest / "cases.json").write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8")
        (dest / "spec.md").write_text(spec, encoding="utf-8")
        frozen.append(task)
        print(f"froze {task}: {len(data['cases'])} cases, {len(data['dropped'])} dropped")
    index = {
        "format": FORMAT,
        "seed": SEED,
        "cases_per_task": args.cases_per_task,
        "python": platform.python_version(),
        "frozen": frozen,
        "skipped": skipped,
    }
    (out / "index.json").write_text(json.dumps(index, indent=2) + "\n")
    if args.chown:
        _chown(out, args.chown)
    return 0


if __name__ == "__main__":
    sys.exit(main())
