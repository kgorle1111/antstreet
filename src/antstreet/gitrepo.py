"""Git as hostile input.

A repository that someone else's agent wrote in is data, not a trusted tool: its `.git/config` can
name programs (`core.fsmonitor`, `filter.<x>.smudge`, `diff.<x>.textconv`), its refs can look like
options, its tree can hold a `.git/` folder. Every call here is an argv list with no shell, run
with a scrubbed environment and `-c core.fsmonitor=false -c core.hooksPath=/dev/null -c
diff.external=`, through plumbing commands only, and a ref only reaches git after `resolve` has
turned it into a commit hash.

`git archive` runs the smudge filters named by the archived tree's `.gitattributes` and defined in
the repository's config, so nothing that reads history runs against the repository itself:
`_object_view` makes an empty bare repository whose only link to the real one is
`objects/info/alternates`. It has the objects and none of the config, refs, replace objects or
hooks. `export`, `diff`, `commits_between` and `is_ancestor` run there.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tarfile
import tempfile
import threading
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from antstreet.redact import safe_text

TIMEOUT_S = 60.0
MAX_OUTPUT_BYTES = 16 * 1024 * 1024  # a diff or a listing; a hostile history can make either huge
MAX_EXPORT_BYTES = 512 * 1024 * 1024  # file bytes in one exported tree
MAX_REF_CHARS = 255
_HEX = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")
_ERROR_CHARS = 300
_ERROR_BYTES = 4096  # stderr kept for a failure message; the rest is read and dropped
_HARDEN = ("-c", "core.fsmonitor=false", "-c", "core.hooksPath=/dev/null", "-c", "diff.external=")
_REF_HINT = "a branch, tag or full commit hash"


class GitError(Exception):
    """A git operation was refused or failed. The message says why and what to try."""


@dataclass(frozen=True, slots=True)
class Commit:
    sha: str
    committed_at: datetime  # the committer date, which the committer chose: a claim, not a proof


def _fail(what: str, why: str, fix: str) -> GitError:
    return GitError(f"{what} failed because {why}; try {fix}")


def _show(text: str) -> str:
    return repr(safe_text(text, limit=80))


def _git_binary() -> str:
    found = shutil.which("git", path="/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin")
    if found is None:
        raise _fail("git", "no `git` program was found", "installing git")
    return found


def _env() -> dict[str, str]:
    """Nothing from the caller's environment reaches git: no GIT_DIR, GIT_EXTERNAL_DIFF,
    GIT_SSH_COMMAND, global or system config, or replace objects."""
    return {
        "PATH": "/usr/bin:/bin",
        "LC_ALL": "C",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_ATTR_NOSYSTEM": "1",
        "GIT_NO_REPLACE_OBJECTS": "1",
        "GIT_OPTIONAL_LOCKS": "0",
        "GIT_TERMINAL_PROMPT": "0",
    }


def _command(
    args: Sequence[str],
    gitdir: Path | None,
    worktree: Path | None,
    config: Sequence[str] = (),
) -> list[str]:
    cmd = [_git_binary(), *_HARDEN]
    for setting in config:
        cmd += ["-c", setting]
    if gitdir is not None:
        cmd.append(f"--git-dir={gitdir}")
    if worktree is not None:
        cmd.append(f"--work-tree={worktree}")
    return [*cmd, *args]


def _popen(
    cmd: list[str], cwd: Path, *, env: dict[str, str] | None = None, **kwargs: Any
) -> subprocess.Popen[bytes]:
    """The one place a process is started."""
    env = _env() if env is None else env
    return subprocess.Popen(cmd, cwd=cwd, env=env, stdin=subprocess.DEVNULL, **kwargs)


def _drain(stream: Any, keep: list[bytes]) -> None:
    """Keep the first `_ERROR_BYTES` of a stream; read the rest away so the child never blocks."""
    keep.append(stream.read(_ERROR_BYTES))
    while stream.read(65536):
        pass


def _run(
    args: Sequence[str],
    *,
    gitdir: Path | None,
    cwd: Path,
    worktree: Path | None = None,
    ok: tuple[int, ...] = (0,),
    timeout_s: float = TIMEOUT_S,
    config: Sequence[str] = (),
    env: dict[str, str] | None = None,
) -> tuple[int, bytes]:
    proc = _popen(
        _command(args, gitdir, worktree, config),
        cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert proc.stdout is not None and proc.stderr is not None
    timed_out = threading.Event()

    def expire() -> None:
        timed_out.set()
        proc.kill()

    timer = threading.Timer(timeout_s, expire)
    err: list[bytes] = []
    drain = threading.Thread(target=_drain, args=(proc.stderr, err), daemon=True)
    chunks: list[bytes] = []
    size = 0
    try:
        timer.start()
        drain.start()
        while chunk := proc.stdout.read1(65536):  # type: ignore[attr-defined]
            size += len(chunk)
            if size > MAX_OUTPUT_BYTES:
                break
            chunks.append(chunk)
    finally:
        timer.cancel()
        if size > MAX_OUTPUT_BYTES:
            proc.kill()
        proc.wait()
        drain.join()
        proc.stdout.close()
        proc.stderr.close()
    if timed_out.is_set():
        raise _fail(
            f"git {args[0]}", f"it ran longer than {timeout_s:.0f}s", "a smaller range"
        ) from None
    if size > MAX_OUTPUT_BYTES:
        raise _fail(f"git {args[0]}", "its output is over the size cap", "a smaller range")
    if proc.returncode not in ok:
        text = (err[0] if err else b"").decode("utf-8", "replace").strip()
        why = safe_text(text, limit=_ERROR_CHARS)
        raise _fail(f"git {args[0]}", why or f"it exited {proc.returncode}", "checking the repo")
    return proc.returncode, b"".join(chunks)


def _gitdir(repo: Path) -> Path:
    """`<repo>/.git`, or what a linked worktree's `.git` file points at. Never discovered by git,
    which would walk up to a parent repository or follow `core.worktree`."""
    dot = Path(repo).resolve() / ".git"
    if dot.is_dir() and not dot.is_symlink():
        return dot
    if dot.is_file() and not dot.is_symlink():
        head = dot.read_text(encoding="utf-8", errors="replace")[:4096].splitlines()[:1]
        if head and head[0].startswith("gitdir: "):
            target = (dot.parent / head[0].removeprefix("gitdir: ").strip()).resolve()
            if target.is_dir():
                return target
    raise _fail(
        f"opening {_show(str(repo))}",
        "it is not the top folder of a git checkout",
        "the folder that contains `.git`",
    )


def _objects_dir(gitdir: Path) -> Path:
    common = gitdir / "commondir"
    if common.is_file():
        gitdir = (gitdir / common.read_text(encoding="utf-8").strip()).resolve()
    return gitdir / "objects"


def _never_committed(gitdir: Path | None, root: Path) -> bool:
    """No commit reachable from a ref and no commit object at all: a brand-new repo. A deleted
    branch or other lost history leaves unreachable commits that `fsck` still finds, so those
    keep the general message (and a hint to recover rather than start over). Only runs on this
    error path, so fsck's cost on a large repo does not matter."""
    if _run(["rev-list", "-n", "1", "--all"], gitdir=gitdir, cwd=root)[1]:
        return False
    _, found = _run(
        ["fsck", "--unreachable", "--no-reflogs", "--no-progress"],
        gitdir=gitdir, cwd=root, ok=(0, 1, 2),
    )  # fmt: skip
    return not any(line.split()[1:2] == [b"commit"] for line in found.splitlines())


def resolve(repo: Path, ref: str) -> str:
    """The commit hash `ref` names. `ref` must be a branch, tag or hash: revision expressions
    (`HEAD~1`, `a..b`, `x:path`, `@{u}`) fail `check-ref-format` and are refused."""
    if not isinstance(ref, str) or not ref or len(ref) > MAX_REF_CHARS or "\x00" in ref:
        raise _fail("reading a ref", "it is empty, too long or has a NUL byte", _REF_HINT)
    if ref.startswith("-"):
        raise _fail(
            "reading a ref",
            f"{_show(ref)} starts with '-', which git reads as an option",
            _REF_HINT,
        )
    root = Path(repo).resolve()
    gitdir = _gitdir(root)
    code, _ = _run(
        ["check-ref-format", "--allow-onelevel", ref], gitdir=gitdir, cwd=root, ok=(0, 1)
    )
    if code != 0:
        raise _fail(
            "reading a ref", f"{_show(ref)} is not a plain branch, tag or hash name", _REF_HINT
        )
    _, out = _run(
        ["rev-parse", "--verify", "--end-of-options", f"{ref}^{{commit}}"],
        gitdir=gitdir, cwd=root, ok=(0, 128),
    )  # fmt: skip
    sha = out.decode("ascii", "replace").strip()
    if not _HEX.fullmatch(sha):
        if ref == "HEAD" and _never_committed(gitdir, root):
            raise _fail(  # a brand-new repo: the first thing a new user often hits
                "reading HEAD",
                "this repo has no commits yet",
                "committing your code first (`git add -A && git commit -m start`), then run this "
                "again",
            )
        raise _fail(
            "reading a ref", f"{_show(ref)} names no commit in this repo", "`git branch -a`"
        )
    return sha


_CONFIG_VALUES = {
    "core.fileMode": ("bool", ("true", "false")),
    "core.ignoreCase": ("bool", ("true", "false")),
    "core.autocrlf": (None, ("true", "false", "input")),
}


def _config_env() -> dict[str, str]:
    """The scrubbed environment plus where the caller's own global config lives, for reading
    values only: `git config --get` runs no program."""
    env = _env()
    del env["GIT_CONFIG_GLOBAL"]
    for name in ("HOME", "XDG_CONFIG_HOME", "GIT_CONFIG_GLOBAL"):
        if name in os.environ:
            env[name] = os.environ[name]
    return env


def _config_get(root: Path, gitdir: Path, key: str, kind: str | None) -> str | None:
    """A value from the repository's own config file (which wins) or else the caller's global one.
    A value git cannot read, or an include, is simply absent."""
    flag = [f"--type={kind}"] if kind else []
    for where in (["--file", str(gitdir / "config")], ["--global"]):
        code, out = _run(
            ["config", *where, *flag, "--get", key],
            gitdir=None, cwd=root, ok=(0, 1, 128), env=_config_env(),
        )  # fmt: skip
        if code == 0:
            return out.decode("utf-8", "replace").strip()
    return None


def _view_settings(root: Path, gitdir: Path) -> tuple[list[str], list[str]]:
    """(`-c` overrides, ls-files arguments) carrying over how the real repository ignores files and
    reads file modes. Only whitelisted values of three settings are copied, and the ignore file as
    a path git reads patterns from. Nothing that names a program (filters, fsmonitor, hooks,
    textconv, external diff) is read."""
    config: list[str] = []
    for key, (kind, allowed) in _CONFIG_VALUES.items():
        value = _config_get(root, gitdir, key, kind)
        if value is not None and value.lower() in allowed:
            config.append(f"{key}={value.lower()}")
    excludes = _config_get(root, gitdir, "core.excludesFile", "path")
    if excludes and "\n" not in excludes:
        path = Path(excludes)
        if path.is_absolute() and path.is_file() and os.access(path, os.R_OK):
            return config, [f"--exclude-from={path}"]
    return config, []


def is_clean(repo: Path) -> bool:
    """No staged change, modified or deleted tracked file, or untracked file that is not ignored.

    Plumbing only and read-only. It runs in an object view holding a copy of the index, not in the
    repository: comparing a file with the index runs its `clean` filter when the timestamp moved,
    and the repository's config is what defines filters. With no config in the view a filter named
    by `.gitattributes` is skipped. The settings that decide what counts as a change or as ignored
    (`core.excludesFile`, `fileMode`, `autocrlf`, `ignoreCase`) are read and passed in as
    whitelisted values. `ls-files` compares content, so `touch` is not a change. Submodule contents
    are not looked into; a split index is refused with git's message.
    """
    root = Path(repo).resolve()
    head = resolve(root, "HEAD")
    config, excludes = _view_settings(root, _gitdir(root))
    with _object_view(root, with_index=True) as (view, cwd):
        code, _ = _run(
            ["diff-index", "--cached", "--quiet", head, "--"],
            gitdir=view, worktree=root, cwd=root, ok=(0, 1), config=config,
        )  # fmt: skip
        if code != 0:
            return False
        _, out = _run(
            ["ls-files", "-z", "--modified", "--others", "--exclude-standard", *excludes],
            gitdir=view, worktree=root, cwd=root, config=config,
        )  # fmt: skip
    return not out


@contextmanager
def _object_view(repo: Path, *, with_index: bool = False) -> Iterator[tuple[Path, Path]]:
    """(git dir, cwd) of a temporary bare repository that borrows the real one's objects only.

    `with_index` also copies the real index and `info/exclude` (files, never config), for the
    questions that compare the working tree with them.
    """
    root = Path(repo).resolve()
    gitdir = _gitdir(root)
    _, fmt = _run(["rev-parse", "--show-object-format"], gitdir=gitdir, cwd=root)
    object_format = fmt.decode("ascii", "replace").strip()
    if object_format not in ("sha1", "sha256"):
        raise _fail("reading the repo", f"its object format is {_show(object_format)}", "sha1")
    objects = _objects_dir(gitdir)
    if "\n" in str(objects) or not objects.is_dir():
        raise _fail("reading the repo", "its object folder is missing or oddly named", "a checkout")
    with tempfile.TemporaryDirectory(prefix="boss_git_") as tmp:
        view = Path(tmp) / "view.git"
        _run(
            ["init", "--bare", "-q", "--template=", f"--object-format={object_format}", str(view)],
            gitdir=None, cwd=Path(tmp),
        )  # fmt: skip
        (view / "objects" / "info").mkdir(parents=True, exist_ok=True)
        (view / "objects" / "info" / "alternates").write_text(f"{objects}\n", encoding="utf-8")
        if with_index:
            _copy_if_file(gitdir / "index", view / "index")
            _copy_if_file(objects.parent / "info" / "exclude", view / "info" / "exclude")
        yield view, Path(tmp)


def _copy_if_file(src: Path, dst: Path) -> None:
    if src.is_file() and not src.is_symlink():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)


def _commit_pair(repo: Path, base: str, head: str) -> tuple[str, str]:
    return resolve(repo, base), resolve(repo, head)


def is_ancestor(repo: Path, base: str, head: str) -> bool:
    """True when `base` is `head` or one of its ancestors."""
    a, b = _commit_pair(repo, base, head)
    with _object_view(repo) as (view, cwd):
        code, _ = _run(["merge-base", "--is-ancestor", a, b], gitdir=view, cwd=cwd, ok=(0, 1))
    return code == 0


def commits_between(repo: Path, base: str, head: str) -> list[Commit]:
    """The commits in `base..head`, oldest first, with their committer dates (UTC)."""
    a, b = _commit_pair(repo, base, head)
    with _object_view(repo) as (view, cwd):
        _, out = _run(
            ["rev-list", "--reverse", "--no-commit-header", "--format=%H %ct", f"{a}..{b}"],
            gitdir=view, cwd=cwd,
        )  # fmt: skip
    commits = []
    for line in out.decode("ascii", "replace").splitlines():
        sha, _, stamp = line.partition(" ")
        if not _HEX.fullmatch(sha) or not stamp.isdigit():
            raise _fail("git rev-list", f"it printed {_show(line)}", "checking the repo")
        commits.append(Commit(sha, datetime.fromtimestamp(int(stamp), UTC)))
    return commits


def diff(repo: Path, base: str, head: str) -> str:
    """The unified diff from `base`'s tree to `head`'s. No external diff program and no text
    conversion filter can run: neither is asked for, and the view has no config to name one."""
    a, b = _commit_pair(repo, base, head)
    with _object_view(repo) as (view, cwd):
        _, out = _run(
            ["diff-tree", "-p", "-r", "--no-ext-diff", "--no-textconv", "--no-color", a, b, "--"],
            gitdir=view, cwd=cwd,
        )  # fmt: skip
    return out.decode("utf-8", "replace")


def _bad_member(name: str) -> str | None:
    parts = PurePosixPath(name).parts
    if not parts or any(p.lower() == ".git" for p in parts):
        return "a path with a `.git` folder or no name"
    return None


def export(repo: Path, sha: str, dest: Path) -> None:
    """Write the tree of commit `sha` into the new or empty folder `dest`, through `git archive`.

    Nothing is checked out: the working tree, index and refs of `repo` are not touched. A tree
    holding a `.git` path, a link out of `dest`, a device file or more than `MAX_EXPORT_BYTES` is
    refused and `dest` is removed if this call created it.
    """
    commit = resolve(repo, sha)
    dest = Path(dest)
    if dest.exists() and (not dest.is_dir() or any(dest.iterdir())):
        raise _fail(f"exporting to {_show(str(dest))}", "it is not an empty folder", "a new path")
    created = not dest.exists()
    dest.mkdir(parents=True, exist_ok=True)
    try:
        with _object_view(repo) as (view, cwd), tempfile.TemporaryFile() as err:
            proc = _popen(
                _command(["archive", "--format=tar", commit], view, None),
                cwd, stdout=subprocess.PIPE, stderr=err,
            )  # fmt: skip
            assert proc.stdout is not None
            refusal: tarfile.TarError | None = None
            try:
                _extract(proc.stdout, dest)
            except tarfile.TarError as exc:
                refusal = exc
            finally:
                proc.stdout.close()
                try:
                    code = proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    code = proc.wait()
            if code != 0 or refusal is not None:
                err.seek(0)
                said = err.read(2000).decode("utf-8", "replace").strip()
                why = safe_text(said or str(refusal or f"it exited {code}"), limit=_ERROR_CHARS)
                raise _fail(
                    "exporting",
                    f"git archive or the tar it wrote was refused ({why})",
                    "a tree without it",
                )
    except BaseException:
        if created:
            shutil.rmtree(dest, ignore_errors=True)
        raise


def _extract(stream: Any, dest: Path) -> None:
    """Unpack a tar stream under `dest`. A member the `data` filter refuses raises a `TarError`."""
    total = 0
    with tarfile.open(fileobj=stream, mode="r|") as tar:
        for member in tar:
            bad = _bad_member(member.name)
            if bad is None and (member.isdev() or member.isfifo()):
                bad = "a device or pipe"
            if bad:
                raise _fail("exporting", f"{_show(member.name)} is {bad}", "a tree without it")
            total += max(member.size, 0)
            if total > MAX_EXPORT_BYTES:
                raise _fail("exporting", "the tree is over the size cap", "a smaller base")
            tar.extract(member, dest, filter="data")
