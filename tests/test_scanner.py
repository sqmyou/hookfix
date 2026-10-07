"""Tests for the static scanner."""

from __future__ import annotations

import pytest

from hookfix.errors import ScanError
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


def test_scan_keeps_fully_qualified_names(tmp_path):
    # PyInstaller needs the exact module path, so ``import a.b`` and
    # ``from a import c`` must not be flattened to ``a``.
    (tmp_path / "mod.py").write_text("import xml.etree\nfrom a import c\n")
    result = scan(tmp_path)
    assert "xml.etree" in result.imports
    assert "a.c" in result.imports


def test_scan_has_no_reachable_set_without_entry(tmp_path):
    (tmp_path / "app.py").write_text("import csv\n")
    result = scan(tmp_path)
    assert result.reachable == []
    assert result.entry is None


def test_scan_reachable_follows_static_imports(tmp_path):
    (tmp_path / "app.py").write_text("import csv\nimport helper\n")
    (tmp_path / "helper.py").write_text("import json\n")
    result = scan(tmp_path, entry=tmp_path / "app.py")
    assert set(result.reachable) >= {"app", "csv", "helper", "json"}


def test_scan_reachable_excludes_unimported_files(tmp_path):
    """A file nothing imports is scanned but is not reachable."""
    (tmp_path / "app.py").write_text("import csv\n")
    (tmp_path / "orphan.py").write_text("import numpy\n")
    result = scan(tmp_path, entry=tmp_path / "app.py")
    assert "numpy" in result.imports
    assert "orphan" not in result.reachable


def test_scan_reachable_follows_package_imports_from_init(tmp_path):
    """Reaching a package covers what its ``__init__`` imports."""
    (tmp_path / "app.py").write_text("import pkg\n")
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("from . import sub\n")
    (pkg / "sub.py").write_text("VALUE = 1\n")
    result = scan(tmp_path, entry=tmp_path / "app.py")
    assert "pkg.sub" in result.reachable


def test_scan_reachable_adds_parent_packages(tmp_path):
    """Importing ``a.b.c`` executes ``a`` and ``a.b``, so both are reachable."""
    (tmp_path / "app.py").write_text("import a.b.c\n")
    a = tmp_path / "a"
    b = a / "b"
    b.mkdir(parents=True)
    (a / "__init__.py").write_text("")
    (b / "__init__.py").write_text("")
    (b / "c.py").write_text("VALUE = 1\n")
    result = scan(tmp_path, entry=tmp_path / "app.py")
    assert {"a", "a.b", "a.b.c"} <= set(result.reachable)


def test_scan_reachable_does_not_follow_dynamic_package(tmp_path):
    """The regression case: a dynamically loaded package stays unreachable.

    ``dynpkg`` is loaded by name, so ``dynpkg`` and its submodule must not be
    in the reachable set even though the scanner reads both files.
    """
    (tmp_path / "app.py").write_text(
        "import importlib\nimportlib.import_module('dynpkg')\n"
    )
    pkg = tmp_path / "dynpkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("from . import helper\n")
    (pkg / "helper.py").write_text("VALUE = 1\n")
    result = scan(tmp_path, entry=tmp_path / "app.py")
    assert "dynpkg.helper" in result.imports
    assert "dynpkg" not in result.reachable
    assert "dynpkg.helper" not in result.reachable


def test_scan_reachable_from_entry_outside_tree(tmp_path):
    root = tmp_path / "src"
    root.mkdir()
    (root / "helper.py").write_text("VALUE = 1\n")
    entry = tmp_path / "app.py"
    entry.write_text("import helper\n")
    result = scan(root, entry=entry)
    assert "helper" in result.reachable


def test_scan_rejects_missing_entry(tmp_path):
    (tmp_path / "app.py").write_text("import csv\n")
    with pytest.raises(ScanError):
        scan(tmp_path, entry=tmp_path / "nope.py")


def test_resolve_relative():
    from hookfix.scanner import _resolve_relative

    # From ``pkg.mod``, ``.`` is ``pkg``.
    assert _resolve_relative("pkg", 1, None) == "pkg"
    assert _resolve_relative("pkg", 1, "sib") == "pkg.sib"
    # ``..`` climbs one level.
    assert _resolve_relative("pkg.sub", 2, "top") == "pkg.top"
    # Climbing above the root cannot resolve.
    assert _resolve_relative("pkg", 3, "x") == ""
    # A top-level module has no package to be relative to.
    assert _resolve_relative("", 1, "x") == "x"
