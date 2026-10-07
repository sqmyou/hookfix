"""End-to-end CLI tests against the dynamic-import fixture."""

from __future__ import annotations

import json

from hookfix.cli import main

from .conftest import DYNAMIC_APP, DYNAMIC_APP_ENTRY


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
    assert data["schema_version"] == 1
    assert "modules" in data


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
            str(DYNAMIC_APP_ENTRY),
            "--path",
            str(DYNAMIC_APP),
            "--quiet",
            "--trace-out",
            str(trace_file),
        ]
    )
    capsys.readouterr()
    code = main(["fix", str(trace_file), "--path", str(DYNAMIC_APP), "--module", "app"])
    out = capsys.readouterr().out
    assert code == 0
    assert "hiddenimports = [" in out
    assert "'plugins.report'," in out


def test_fix_writes_to_file(capsys, tmp_path):
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
    output = tmp_path / "hook-app.py"
    code = main(
        ["fix", str(trace_file), "--path", str(DYNAMIC_APP), "-o", str(output), "--module", "app"]
    )
    assert code == 0
    assert "'plugins.report'," in output.read_text()


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
