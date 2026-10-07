"""Tests for the runtime tracer and log parsing."""

from __future__ import annotations

from hookfix.tracer import parse_audit_log, traced_run


def test_parse_audit_log_reads_names_and_origins():
    text = "csv\t/usr/lib/csv.py\nplugins\nplugins.report\t/app/plugins/report.py\n"
    modules, origins = parse_audit_log(text)
    assert modules == {"csv", "plugins", "plugins.report"}
    assert origins["csv"] == "/usr/lib/csv.py"
    assert origins["plugins.report"] == "/app/plugins/report.py"
    assert "plugins" not in origins


def test_parse_audit_log_ignores_blank_lines():
    modules, origins = parse_audit_log("\n\ncsv\n\n")
    assert modules == {"csv"}
    assert origins == {}


def test_traced_run_captures_dynamic_import(tmp_path):
    """The whole point: a module imported via importlib must be recorded."""
    package = tmp_path / "somepkg"
    package.mkdir()
    (package / "__init__.py").write_text("")
    (package / "inner.py").write_text("VALUE = 1\n")

    script = tmp_path / "run.py"
    script.write_text(
        "import importlib\n"
        "import sys\n"
        f"sys.path.insert(0, {str(tmp_path)!r})\n"
        "importlib.import_module('somepkg.inner')\n"
    )

    def target() -> int:
        import runpy

        runpy.run_path(str(script), run_name="__main__")
        return 0

    tracer, code = traced_run(target)
    assert code == 0
    assert "somepkg.inner" in tracer.modules


def test_traced_run_reports_system_exit_code(tmp_path):
    script = tmp_path / "exit.py"
    script.write_text("raise SystemExit(3)\n")

    def target() -> int:
        import runpy

        runpy.run_path(str(script), run_name="__main__")
        return 0

    _, code = traced_run(target)
    assert code == 3
