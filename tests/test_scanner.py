"""Tests for the static scanner."""

from __future__ import annotations

from hookfix.scanner import scan

from .conftest import DYNAMIC_APP


def test_scan_finds_static_imports():
    result = scan(DYNAMIC_APP)
    # ``csv`` is imported with a plain import statement in the fixture.
    assert "csv" in result.imports
    assert "importlib" in result.imports


def test_scan_finds_dynamic_sites():
    result = scan(DYNAMIC_APP)
    kinds = {site.kind for site in result.dynamic_sites}
    assert "importlib.import_module" in kinds


def test_scan_records_location_of_dynamic_site():
    result = scan(DYNAMIC_APP)
    site = next(s for s in result.dynamic_sites if s.kind == "importlib.import_module")
    assert site.path == "app.py"
    assert site.lineno > 0


def test_scan_ignores_excluded_directories(tmp_path):
    (tmp_path / "keep.py").write_text("import csv\n")
    hidden = tmp_path / ".venv"
    hidden.mkdir()
    (hidden / "ignored.py").write_text("import numpy\n")
    result = scan(tmp_path)
    assert "csv" in result.imports
    assert "numpy" not in result.imports


def test_scan_handles_unparseable_file(tmp_path):
    (tmp_path / "broken.py").write_text("def (:\n")
    (tmp_path / "good.py").write_text("import csv\n")
    result = scan(tmp_path)
    assert "csv" in result.imports
    assert "broken.py" not in result.files


def test_scan_finds_imports_nested_in_functions(tmp_path):
    (tmp_path / "mod.py").write_text(
        "def lazy():\n    import json\n    return json\n"
    )
    result = scan(tmp_path)
    assert "json" in result.imports
