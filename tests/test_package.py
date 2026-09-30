import shutil
import subprocess

import boss


def test_package_imports_from_installed_src_layout():
    assert boss.__version__ == "0.0.1"


def test_console_script_is_installed_and_runs():
    exe = shutil.which("boss")
    assert exe, "`boss` console script not on PATH; run tests with `uv run pytest`"
    out = subprocess.run([exe, "--version"], capture_output=True, text=True, check=False)
    assert out.returncode == 0
    assert out.stdout.strip() == "boss 0.0.1"
