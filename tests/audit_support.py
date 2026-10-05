"""A small git repository, a fake `claude` that plays the boss and the examiner, and a way to run
`boss audit` against them. Not a test module.

The repository holds `slug.py` (`slugify` lower-cases; `shout` upper-cases) and a `tests/` folder.
The request asks `slugify` to collapse runs of symbols into one hyphen and trim the ends. The fake
boss writes four checks for it: two fail on the base and are counted (`c01`, `c02`), one passes on
the base (`c03`), one needs a library nobody has (`c04`).
"""

import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from boss_init import BOSS_INIT

from boss.cli import main

REQUEST = (
    "Make slugify in slug.py collapse every run of characters other than letters and digits into "
    "one hyphen, and trim hyphens from both ends."
)
BASE_SLUG = (
    "def slugify(text):\n    return text.lower()\n\n\ndef shout(text):\n    return text.upper()\n"
)
BASE_TESTS = (
    "from slug import shout, slugify\n\n\n"
    "def test_lower():\n    assert slugify('ABC') == 'abc'\n\n\n"
    "def test_shout():\n    assert shout('abc') == 'ABC'\n"
)
RIGHT_SLUG = (
    "import re\n\n\ndef slugify(text):\n"
    "    return re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-')\n\n\n"
    "def shout(text):\n    return text.upper()\n"
)
WRONG_SLUG = (
    "def slugify(text):\n    return text.lower().replace(' ', '-')\n\n\n"
    "def shout(text):\n    return text.upper()\n"
)
# Right for both failing checks; breaks `shout` as well, and the test of `shout` is deleted.
SNEAKY_SLUG = RIGHT_SLUG.replace("return text.upper()", "return text")
# Right except for one word, which a check that passes on the base guards.
GUARD_SLUG = RIGHT_SLUG.replace(
    "    return re.sub", "    if text == 'abc':\n        return 'ABC'\n    return re.sub"
)
# Needs a library this machine has not got.
NEEDS_LIB_SLUG = "import quuxlib_zq\n\n" + RIGHT_SLUG
# Hangs past a shortened gate timeout (see `short_timeout_for_hangs`).
HANGS_SLUG = "import time\n\ntime.sleep(60)\n" + RIGHT_SLUG
MARKER = "zq-marker-8d41f2"  # a literal inside a sealed check; it must never appear in the repo
C01 = (
    "from slug import slugify\n\n\n"
    "def test_collapses_runs_of_symbols():\n    assert slugify('Hello,  World') == 'hello-world'\n"
)
C02 = (
    "from slug import slugify\n\n\n"
    f"def test_trims_both_ends():\n    assert slugify('  Zq Marker 8d41f2! ') == '{MARKER}'\n"
)
C03 = (
    "from slug import slugify\n\n\n"
    "def test_plain_word_is_unchanged():\n    assert slugify('abc') == 'abc'\n"
)
C04 = (
    "import nosuchlib_zq\nfrom slug import slugify\n\n\n"
    "def test_uses_the_library():\n    assert slugify('a') == nosuchlib_zq.A\n"
)
DRAFT = {
    "tasks": [{"id": "t1", "brief": "make slugify collapse runs", "paths": ["."]}],
    "checks": [
        {"description": "runs of symbols become one hyphen", "task": "t1", "code": C01},
        {"description": "hyphens are trimmed at both ends", "task": "t1", "code": C02},
        {"description": "a plain word is unchanged", "task": "t1", "code": C03},
        {"description": "needs a library", "task": "t1", "code": C04},
    ],
}
H01 = (
    "from slug import slugify\n\n\n"
    "def test_held_out_double_hyphen():\n    assert slugify('a--b') == 'a-b'\n"
)
EXAMINED = {
    "checks": [
        {"id": "h01", "source": "collapse every run of characters other than letters and digits",
         "code": H01}
    ]
}  # fmt: skip
INIT = json.dumps(BOSS_INIT)
FAKE_CLAUDE = f"""#!{sys.executable}
import json, os, sys
argv = sys.argv[1:]
home = os.environ["HOME"]
n = len([f for f in os.listdir(home) if f.startswith("argv_")])
open(os.path.join(home, f"argv_{{n}}.json"), "w").write(json.dumps(argv))
schema = argv[argv.index("--json-schema") + 1]
which = "audit_examiner.json" if '"source"' in schema else "audit_draft.json"
draft = json.load(open(os.path.join(home, which)))
usage = {{"m": {{"inputTokens": 10, "outputTokens": 5, "cacheReadInputTokens": 0}}}}
print({INIT!r}, flush=True)
print(json.dumps({{"type": "result", "subtype": "success", "is_error": False,
                  "terminal_reason": "completed", "modelUsage": usage, "session_id": "s-1",
                  "total_cost_usd": 0.004, "structured_output": draft}}), flush=True)
"""

LONG_AGO = datetime(2020, 1, 1, tzinfo=UTC)


def later() -> datetime:
    """A committer date safely after any seal made in this test run."""
    return datetime.now(UTC) + timedelta(hours=1)


def git(repo: Path, *args: str, when: datetime | None = None) -> str:
    """Plain git for building fixtures. The repository's own config is not honoured, so a hostile
    config a test plants later cannot run during setup."""
    env = {
        "PATH": "/usr/bin:/bin",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@example.com",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@example.com",
    }
    if when is not None:
        env["GIT_COMMITTER_DATE"] = env["GIT_AUTHOR_DATE"] = when.isoformat()
    done = subprocess.run(
        ["git", "-c", "core.fsmonitor=false", "-C", str(repo), *args],
        env=env, capture_output=True, text=True, check=False,
    )  # fmt: skip
    if done.returncode:
        raise RuntimeError(f"git {' '.join(args)} failed: {done.stderr.strip()}")
    return done.stdout.strip()


def init_repo(path: Path) -> str:
    """The base commit, on branch `main`; returns its hash."""
    path.mkdir(parents=True)
    git(path, "init", "-q", "-b", "main")
    write(path, "slug.py", BASE_SLUG)
    write(path, "tests/test_slug.py", BASE_TESTS)
    git(path, "add", "-A")
    git(path, "commit", "-q", "-m", "base", when=LONG_AGO)
    return git(path, "rev-parse", "HEAD")


def write(repo: Path, relative: str, text: str) -> None:
    target = repo / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text)


def branch(repo: Path, name: str, files: dict[str, str | None], when: datetime) -> str:
    """A branch off `main` with these files written (None deletes one); back on `main` after."""
    git(repo, "checkout", "-q", "-b", name, "main")
    for relative, text in files.items():
        if text is None:
            (repo / relative).unlink()
        else:
            write(repo, relative, text)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", name, when=when)
    sha = git(repo, "rev-parse", "HEAD")
    git(repo, "checkout", "-q", "main")
    return sha


class Audit:
    """`boss audit` run against a fake boss, with the store under a throwaway home."""

    def __init__(self, folder: Path) -> None:
        self.folder = folder
        self.home = folder / "home"
        self.home.mkdir(parents=True, exist_ok=True)
        self.fake = folder / "fake-claude"
        self.fake.write_text(FAKE_CLAUDE)
        self.fake.chmod(0o755)
        self.set_draft(DRAFT)
        self.repo = folder / "repo"
        self.base = init_repo(self.repo)
        self.request = folder / "request.txt"
        self.request.write_text(REQUEST)

    @property
    def store(self) -> Path:
        return self.home / ".boss-audit"

    def set_draft(self, draft: dict, name: str = "audit_draft.json") -> None:
        (self.home / name).write_text(json.dumps(draft))

    def environ(self, **extra: str) -> dict[str, str]:
        return {
            "PATH": "/usr/bin:/bin",
            "HOME": str(self.home),
            "BOSS_CLAUDE_BIN": str(self.fake),
            **extra,
        }

    def run(self, *argv: str, answers: tuple[str, ...] = ("a",), **env: str) -> tuple[int, str]:
        said: list[str] = []
        replies = iter(answers)
        code = main(
            ["audit", *argv],
            ask=lambda prompt: next(replies),
            say=said.append,
            environ=self.environ(**env),
        )
        return code, "\n".join(said)

    def plan(self, *extra: str, base: str = "main", **kw) -> tuple[int, str]:
        return self.run(
            "plan", "--repo", str(self.repo), "--request", str(self.request), f"--base={base}",
            *extra, **kw,
        )  # fmt: skip

    def check(self, run_id: str, head: str, *extra: str, **kw) -> tuple[int, str]:
        return self.run("check", run_id, f"--head={head}", "--repo", str(self.repo), *extra, **kw)

    def run_id(self) -> str:
        [run] = sorted((self.store / ".boss" / "runs").iterdir())
        return run.name

    def prompts(self) -> list[list[str]]:
        files = sorted(self.home.glob("argv_*.json"))
        return [json.loads(f.read_text()) for f in files]


def short_timeout_for_hangs(monkeypatch) -> None:
    """Gate runs of a tree whose slug.py sleeps time out after 3s; every other run is unchanged."""
    import boss.audit as audit_module

    real = audit_module.run_gate

    def gate(tree, checks_dir, checks, **kw):
        if "time.sleep" in (Path(tree) / "slug.py").read_text():
            kw["timeout_s"] = 3.0
        return real(tree, checks_dir, checks, **kw)

    monkeypatch.setattr(audit_module, "run_gate", gate)
