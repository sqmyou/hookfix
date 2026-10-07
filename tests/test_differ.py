"""Tests for the diff engine."""

from __future__ import annotations

import pytest

from hookfix.differ import diff
from hookfix.model import StaticResult, TraceResult


def test_diff_reports_runtime_only_module():
    trace = TraceResult(modules=["plugins", "plugins.report", "csv"])
    static = StaticResult(imports=["csv"], reachable=["app", "csv"], files=["app.py"])
    result = diff(trace, static)
    # The fully-qualified submodule is reported; the bare parent package is
    # suppressed because importing the submodule pulls it in.
    assert result.missing == ["plugins.report"]
    assert "csv" in result.common


def test_diff_reports_bare_package_when_no_submodule():
    trace = TraceResult(modules=["plugins"])
    static = StaticResult(imports=[], reachable=["app"], files=[])
    result = diff(trace, static)
    assert result.missing == ["plugins"]


def test_diff_separates_stdlib_from_third_party():
    trace = TraceResult(modules=["csv", "json", "requests"])
    static = StaticResult(imports=[], reachable=["app"], files=[])
    result = diff(trace, static)
    # ``json`` is standard library, ``requests`` is not.
    assert "json" in result.stdlib_only
    assert "requests" in result.missing


def test_diff_filters_import_machinery_noise():
    trace = TraceResult(modules=["_csv", "importlib._bootstrap", "hookfix.tracer", "requests"])
    static = StaticResult(imports=[], reachable=["app"], files=[])
    result = diff(trace, static)
    assert result.missing == ["requests"]


def test_diff_is_empty_when_nothing_is_hidden():
    trace = TraceResult(modules=["csv"])
    static = StaticResult(imports=["csv"], reachable=["app", "csv"], files=["app.py"])
    result = diff(trace, static)
    assert result.missing == []


def test_diff_reports_import_of_unreachable_file():
    """A module the scan saw but nothing imports is still missing.

    This is the regression that matters: the old differ compared against every
    import in the tree, so ``dynpkg.helper`` -- read from ``dynpkg/__init__.py``
    but never reached from the entry point -- was silently treated as covered.
    """
    trace = TraceResult(modules=["dynpkg", "dynpkg.helper"])
    # ``dynpkg.helper`` is in ``imports`` (the scanner read the file) but not in
    # ``reachable`` (nothing statically imports it from the entry point).
    static = StaticResult(
        imports=["dynpkg.helper"],
        reachable=["app"],
        files=["app.py", "dynpkg/__init__.py", "dynpkg/helper.py"],
    )
    result = diff(trace, static)
    assert result.missing == ["dynpkg.helper"]
    assert "dynpkg" not in result.common


def test_diff_treats_reachable_submodule_as_covered():
    trace = TraceResult(modules=["dynpkg.helper"])
    static = StaticResult(imports=["dynpkg.helper"], reachable=["app", "dynpkg.helper"], files=[])
    result = diff(trace, static)
    assert result.missing == []
    assert "dynpkg.helper" in result.common


def test_diff_rejects_scan_without_entry_point():
    trace = TraceResult(modules=["requests"])
    static = StaticResult(imports=[], files=[])
    with pytest.raises(ValueError, match="reachable set"):
        diff(trace, static)
