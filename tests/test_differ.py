"""Tests for the diff engine."""

from __future__ import annotations

from hookfix.differ import diff
from hookfix.model import StaticResult, TraceResult


def test_diff_reports_runtime_only_module():
    trace = TraceResult(modules=["plugins", "plugins.report", "csv"])
    static = StaticResult(imports=["csv"], files=["app.py"])
    result = diff(trace, static)
    assert result.missing == ["plugins"]
    assert "csv" in result.common


def test_diff_separates_stdlib_from_third_party():
    trace = TraceResult(modules=["csv", "json", "requests"])
    static = StaticResult(imports=[], files=[])
    result = diff(trace, static)
    # ``json`` is standard library, ``requests`` is not.
    assert "json" in result.stdlib_only
    assert "requests" in result.missing


def test_diff_filters_import_machinery_noise():
    trace = TraceResult(modules=["_csv", "importlib._bootstrap", "hookfix.tracer", "requests"])
    static = StaticResult(imports=[], files=[])
    result = diff(trace, static)
    assert result.missing == ["requests"]


def test_diff_is_empty_when_nothing_is_hidden():
    trace = TraceResult(modules=["csv"])
    static = StaticResult(imports=["csv"], files=["app.py"])
    result = diff(trace, static)
    assert result.missing == []
