"""Tests for the runtime tracer and log parsing."""

from __future__ import annotations

from hookfix.tracer import parse_audit_log, parse_spawn_sites, traced_run


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


def test_parse_audit_log_ignores_spawn_records():
    # A log mixes import lines and ``@spawn`` records; the import parser must
    # not mistake a record's payload for a module name.
    text = "csv\t/usr/lib/csv.py\n@spawn\tsubprocess.Popen\t/app/app.py\t12\n"
    modules, origins = parse_audit_log(text)
    assert modules == {"csv"}


def test_parse_spawn_sites_reads_path_and_line():
    text = "@spawn\tsubprocess.Popen\t/app/app.py\t12\n"
    sites = parse_spawn_sites(text)
    assert len(sites) == 1
    assert sites[0].event == "subprocess.Popen"
    assert sites[0].path == "/app/app.py"
    assert sites[0].lineno == 12


def test_parse_spawn_sites_collapses_one_line():
    # subprocess.run raises several audit events from the same source line.
    text = (
        "@spawn\tsubprocess.Popen\t/app/app.py\t12\n"
        "@spawn\tos.posix_spawn\t/app/app.py\t12\n"
    )
    sites = parse_spawn_sites(text)
    assert len(sites) == 1


def test_parse_spawn_sites_keeps_two_distinct_lines():
    text = (
        "@spawn\tsubprocess.Popen\t/app/app.py\t12\n"
        "@spawn\tsubprocess.Popen\t/app/app.py\t20\n"
    )
    sites = parse_spawn_sites(text)
    assert [s.lineno for s in sites] == [12, 20]


def test_parse_spawn_sites_tolerates_a_missing_line():
    text = "@spawn\tos.system\t\t\n"
    sites = parse_spawn_sites(text)
    assert sites[0].event == "os.system"
    assert sites[0].path is None
    assert sites[0].lineno is None


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
