"""Integration test: freeze a real app and run the binary.

These are the tests that matter for this project. A hook file that parses is
worthless if PyInstaller never reads it, and a diff that looks right is
worthless if the frozen binary still crashes. Both paths are exercised here
against a real PyInstaller run.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from hookfix.cli import main

from .conftest import HOOKED_APP, HOOKED_APP_ENTRY

pytestmark = pytest.mark.skipif(
    shutil.which("pyinstaller") is None, reason="PyInstaller is not installed"
)


def _freeze(app: Path, work: Path, extra: list[str]) -> Path:
    """Freeze ``app`` in ``work`` and return the resulting executable."""
    work.mkdir(parents=True, exist_ok=True)
    dist = work / "dist"
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--distpath",
        str(dist),
        "--workpath",
        str(work / "build"),
        "--specpath",
        str(work),
        "--name",
        "frozen",
        *extra,
        str(app),
    ]
    subprocess.run(cmd, cwd=work, check=True, capture_output=True)
    exe = dist / "frozen"
    if not exe.exists():
        exe = dist / "frozen.exe"
    return exe


def test_generated_hook_file_makes_the_frozen_binary_work(tmp_path, capsys):
    """The headline claim: the hook file turns a crashing binary into a working one."""
    trace_file = tmp_path / "trace.json"
    main(
        [
            "run",
            str(HOOKED_APP_ENTRY),
            "--path",
            str(HOOKED_APP),
            "--quiet",
            "--trace-out",
            str(trace_file),
        ]
    )
    capsys.readouterr()

    hooks = tmp_path / "hooks"
    hooks.mkdir()
    code = main(["fix", str(trace_file), "--path", str(HOOKED_APP), "-o", str(hooks)])
    assert code == 0
    hook_file = hooks / "hook-dynpkg.py"
    assert hook_file.exists()

    # Baseline: without the hook the dynamic submodule is missing.
    broken = _freeze(HOOKED_APP_ENTRY, tmp_path / "broken", ["--onefile", "--paths", str(HOOKED_APP)])
    result = subprocess.run([str(broken)], capture_output=True, text=True)
    assert result.returncode != 0
    assert "dynpkg" in result.stderr

    # With only the generated hook applied, the binary must work.
    fixed = _freeze(
        HOOKED_APP_ENTRY,
        tmp_path / "fixed",
        [
            "--onefile",
            "--paths",
            str(HOOKED_APP),
            "--additional-hooks-dir",
            str(hooks),
        ],
    )
    result = subprocess.run([str(fixed)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert "helper: helper" in result.stdout


def test_hidden_import_flag_makes_the_frozen_binary_work(tmp_path, capsys):
    """The documented fallback path: --hidden-import, applied by hand."""
    fixed = _freeze(
        HOOKED_APP_ENTRY,
        tmp_path / "flag",
        ["--onefile", "--paths", str(HOOKED_APP), "--hidden-import=dynpkg.helper"],
    )
    result = subprocess.run([str(fixed)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert "helper: helper" in result.stdout
