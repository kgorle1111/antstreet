import shutil
import subprocess

import pytest

import antstreet


def test_package_imports_from_installed_src_layout():
    assert antstreet.__version__ == "0.0.1"


@pytest.mark.parametrize("name", ["antstreet", "boss"])
def test_console_scripts_are_installed_and_print_the_primary_name(name):
    exe = shutil.which(name)
    assert exe, f"`{name}` console script not on PATH; run tests with `uv run pytest`"
    out = subprocess.run([exe, "--version"], capture_output=True, text=True, check=False)
    assert out.returncode == 0
    assert out.stdout.strip() == "antstreet 0.0.1"
