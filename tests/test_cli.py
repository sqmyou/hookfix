"""End-to-end CLI tests against the dynamic-import fixture."""

from __future__ import annotations

import json

from hookfix.cli import main

from .conftest import (
    DYNAMIC_APP,
    DYNAMIC_APP_ENTRY,
    HOOKED_APP,
    HOOKED_APP_ENTRY,
    NESTED_APP,
    NESTED_APP_ENTRY,
    NESTED_PKG_APP,
    NESTED_PKG_APP_ENTRY,
    PKG_APP,
    PKG_APP_ENTRY,
    PRIVATE_APP,
    PRIVATE_APP_ENTRY,
    TWO_PKGS_APP,
    TWO_PKGS_APP_ENTRY,
)


def test_run_reports_hidden_import(capsys):
    code = main(
        [
            "run",
            str(DYNAMIC_APP_ENTRY),
            "--path",
            str(DYNAMIC_APP),
            "--quiet",
        ]
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "Hidden imports (1)" in out
    assert "plugins" in out


def test_run_json_output(capsys):
    code = main(
        [
            "run",
            str(DYNAMIC_APP_ENTRY),
            "--path",
            str(DYNAMIC_APP),
            "--quiet",
            "--json",
        ]
    )
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert "plugins.report" in payload["missing"]


def test_run_writes_trace(capsys, tmp_path):
    trace_file = tmp_path / "trace.json"
    main(
        [
            "run",
            str(DYNAMIC_APP_ENTRY),
            "--path",
            str(DYNAMIC_APP),
            "--quiet",
            "--trace-out",
            str(trace_file),
        ]
    )
    data = json.loads(trace_file.read_text())
    assert data["schema_version"] == 2
    assert "modules" in data
    assert data["entry"].endswith("app.py")


def test_run_passes_script_arguments(capfd):
    # capfd (not capsys) captures at the file-descriptor level, so it sees the
    # output of the traced script, which runs in a child process.
    code = main(
        [
            "run",
            str(DYNAMIC_APP_ENTRY),
            "--path",
            str(DYNAMIC_APP),
            "--",
            "archive",
        ]
    )
    out = capfd.readouterr().out
    assert code == 0
    assert "archive plugin" in out


def test_fix_emits_hook_file(capsys, tmp_path):
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
    code = main(["fix", str(trace_file), "--path", str(HOOKED_APP)])
    out = capsys.readouterr().out
    assert code == 0
    assert "hiddenimports = [" in out
    assert "'dynpkg.helper'," in out
    # The hook is keyed to the package PyInstaller processes, not the entry
    # script -- a hook named after the script is never read.
    assert "# hook-dynpkg.py" in out


def test_fix_refuses_hook_named_after_the_entry_script(capsys, tmp_path):
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
    code = main(["fix", str(trace_file), "--path", str(HOOKED_APP), "--module", "app"])
    err = capsys.readouterr().err
    assert code == 2
    assert "never" in err and "__main__" in err


def test_fix_rejects_module_nothing_imports(capsys, tmp_path):
    """--module naming an unreachable package must error, not write a dead file.

    A hook only fires for a module PyInstaller processes. If nothing imports the
    name, the hook is never read, so writing it would repeat the original bug.
    """
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
    code = main(["fix", str(trace_file), "--path", str(HOOKED_APP), "--module", "nope"])
    err = capsys.readouterr().err
    assert code == 2
    assert "no hook can cover nope" in err


def test_fix_prints_clean_message_when_nothing_is_hidden(capsys, tmp_path):
    clean = tmp_path / "clean.py"
    clean.write_text("print('hi')\n")
    trace_file = tmp_path / "trace.json"
    main(["run", str(clean), "--path", str(tmp_path), "--quiet", "--trace-out", str(trace_file)])
    capsys.readouterr()
    code = main(["fix", str(trace_file), "--path", str(tmp_path)])
    out = capsys.readouterr().out
    assert code == 0
    assert "no hidden imports" in out


def test_run_reports_private_package_submodule(capsys):
    """A ``_``-prefixed package's dynamic submodule must be reported.

    Regression: the noise filter dropped every ``_``-prefixed name, so
    ``_priv._core`` never appeared and the frozen app died.
    """
    code = main(
        [
            "run",
            str(PRIVATE_APP_ENTRY),
            "--path",
            str(PRIVATE_APP),
            "--quiet",
            "--json",
        ]
    )
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["missing"] == ["_priv._core"]


def test_run_handles_nested_package_entry(capsys):
    """``python -m a.b`` from ``a/b/__main__.py`` resolves the dotted package.

    Regression: the bootstrap returned only the leaf name ``b`` and put the
    package directory on ``sys.path``, so the program could not import ``a``
    and the run died before any trace was written.
    """
    code = main(
        [
            "run",
            str(NESTED_PKG_APP_ENTRY),
            "--path",
            str(NESTED_PKG_APP),
            "--quiet",
            "--json",
        ]
    )
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["missing"] == ["a.b.worker"]


def test_fix_writes_to_directory(capsys, tmp_path):
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
    out_dir = tmp_path / "hooks"
    out_dir.mkdir()
    code = main(["fix", str(trace_file), "--path", str(HOOKED_APP), "-o", str(out_dir)])
    assert code == 0
    written = out_dir / "hook-dynpkg.py"
    assert written.exists()
    assert "'dynpkg.helper'," in written.read_text()


def test_fix_writes_one_hook_per_package(tmp_path, capsys):
    """Two hidden packages get two hooks, each scoped to its own modules."""
    trace_file = tmp_path / "trace.json"
    main(
        [
            "run",
            str(TWO_PKGS_APP_ENTRY),
            "--path",
            str(TWO_PKGS_APP),
            "--quiet",
            "--trace-out",
            str(trace_file),
        ]
    )
    capsys.readouterr()
    hooks = tmp_path / "hooks"
    hooks.mkdir()
    code = main(["fix", str(trace_file), "--path", str(TWO_PKGS_APP), "-o", str(hooks)])
    capsys.readouterr()
    assert code == 0
    alpha = (hooks / "hook-alpha.py").read_text()
    beta = (hooks / "hook-beta.py").read_text()
    # Each hook carries only its own package -- not the union of both.
    assert "'alpha.one'," in alpha and "beta" not in alpha
    assert "'beta.two'," in beta and "alpha" not in beta


def test_diff_from_saved_trace(capsys, tmp_path):
    trace_file = tmp_path / "trace.json"
    main(
        [
            "run",
            str(DYNAMIC_APP_ENTRY),
            "--path",
            str(DYNAMIC_APP),
            "--quiet",
            "--trace-out",
            str(trace_file),
        ]
    )
    capsys.readouterr()
    code = main(["diff", str(trace_file), "--path", str(DYNAMIC_APP), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert "plugins.report" in payload["missing"]


def test_missing_script_reports_error(capsys):
    code = main(["run", "does-not-exist.py"])
    err = capsys.readouterr().err
    assert code == 2
    assert "does not exist" in err


def test_run_reports_module_hidden_behind_a_dynamic_package(capsys):
    """Regression: a submodule reachable only through a dynamic import.

    ``dynpkg`` is imported by name, so a freezer never reads
    ``dynpkg/__init__.py``. The ``helper`` submodule it imports there must be
    reported, even though the scanner reads that file.
    """
    code = main(
        ["run", str(NESTED_APP_ENTRY), "--path", str(NESTED_APP), "--quiet", "--json"]
    )
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert "dynpkg.helper" in payload["missing"]
    assert "dynpkg" not in payload["common"]


def test_fix_reports_module_hidden_behind_a_dynamic_package(capsys, tmp_path):
    trace_file = tmp_path / "trace.json"
    main(
        [
            "run",
            str(NESTED_APP_ENTRY),
            "--path",
            str(NESTED_APP),
            "--quiet",
            "--trace-out",
            str(trace_file),
        ]
    )
    capsys.readouterr()
    code = main(["fix", str(trace_file), "--path", str(NESTED_APP)])
    out = capsys.readouterr().out
    assert code == 0
    # ``dynpkg`` is never imported statically, so PyInstaller never processes
    # it and no hook keyed to it can fire. The module goes to --hidden-import.
    assert "--hidden-import=dynpkg.helper" in out
    assert "no hook file written" in out


def test_diff_rejects_schema_1_trace(capsys, tmp_path):
    trace_file = tmp_path / "old.json"
    trace_file.write_text(
        json.dumps({"schema_version": 1, "modules": ["requests"], "origins": {}})
    )
    code = main(["diff", str(trace_file), "--path", str(DYNAMIC_APP)])
    err = capsys.readouterr().err
    assert code == 2
    assert "no entry point recorded" in err


def test_run_reports_submodule_of_the_entry_package(capsys):
    """An entry point inside its own package must not hide that package's modules.

    Regression from 0.1.1: a reachable parent package was treated as covering
    its submodules, so ``mypkg.worker`` was never reported and the frozen app
    died with ``ModuleNotFoundError: mypkg``.
    """
    code = main(
        [
            "run",
            str(PKG_APP_ENTRY),
            "--path",
            str(PKG_APP),
            "--quiet",
            "--json",
        ]
    )
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["missing"] == ["mypkg.worker"]
