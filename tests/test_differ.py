"""Tests for the diff engine."""

from __future__ import annotations

import pytest

from hookfix.differ import diff
from hookfix.model import StaticResult, TraceResult


def test_diff_reports_runtime_only_module():
    trace = TraceResult(
        modules=["plugins", "plugins.report", "csv"],
        origins={"plugins": "/x/plugins/__init__.py", "plugins.report": "/x/plugins/report.py"},
    )
    static = StaticResult(imports=["csv"], reachable=["app", "csv"], files=["app.py"])
    result = diff(trace, static)
    # The fully-qualified submodule is reported and the bare parent is dropped,
    # because importing the submodule pulls the package in and listing both
    # just clutters the generated config.
    assert result.missing == ["plugins.report"]
    assert "csv" in result.common


def test_diff_does_not_treat_reachable_parent_as_covering_submodule():
    """A reachable package does not cover a submodule only reached at runtime.

    Regression from 0.1.1: ``_covered_by_reachable`` accepted any reachable
    parent, so ``mypkg.worker`` looked covered just because ``mypkg`` was
    reachable. The freeze then died with ``ModuleNotFoundError: mypkg``.
    """
    trace = TraceResult(
        modules=["mypkg", "mypkg.worker"],
        origins={"mypkg": "/x/mypkg/__init__.py", "mypkg.worker": "/x/mypkg/worker.py"},
    )
    static = StaticResult(
        imports=["importlib"],
        reachable=["importlib", "mypkg", "mypkg.__main__"],
        files=["mypkg/__init__.py", "mypkg/__main__.py", "mypkg/worker.py"],
    )
    result = diff(trace, static)
    assert result.missing == ["mypkg.worker"]
    assert "mypkg" in result.common


def test_diff_reports_bare_package_when_no_submodule():
    trace = TraceResult(modules=["plugins"], origins={"plugins": "/x/plugins/__init__.py"})
    static = StaticResult(imports=[], reachable=["app"], files=[])
    result = diff(trace, static)
    assert result.missing == ["plugins"]


def test_diff_separates_stdlib_from_third_party():
    trace = TraceResult(
        modules=["csv", "json", "requests"],
        origins={"requests": "/x/requests/__init__.py"},
    )
    static = StaticResult(imports=[], reachable=["app"], files=[])
    result = diff(trace, static)
    # ``json`` is standard library, ``requests`` is not.
    assert "json" in result.stdlib_only
    assert "requests" in result.missing


def test_diff_filters_import_machinery_noise():
    trace = TraceResult(
        modules=["_csv", "importlib._bootstrap", "hookfix.tracer", "requests"],
        origins={"requests": "/x/requests/__init__.py"},
    )
    static = StaticResult(imports=[], reachable=["app"], files=[])
    result = diff(trace, static)
    assert result.missing == ["requests"]


def test_diff_keeps_package_that_shares_a_filter_prefix():
    """A real package whose name starts with a filtered prefix must survive.

    Regression: ``_is_noise`` used ``startswith("importlib")`` and
    ``startswith("hookfix")``, so ``importlib_resources`` (a real, widely used
    package) and any ``hookfix_*`` name were dropped from the report entirely.
    The user got a clean bill of health and a binary that crashed. Matching is
    on the exact top-level name now, so the machinery internals are still
    filtered but lookalikes are not.
    """
    trace = TraceResult(
        modules=[
            "importlib",
            "importlib._bootstrap",
            "importlib_resources",
            "hookfix_extra",
            "hookfix.tracer",
        ],
        origins={
            "importlib_resources": "/x/importlib_resources/__init__.py",
            "hookfix_extra": "/x/hookfix_extra/__init__.py",
        },
    )
    static = StaticResult(imports=[], reachable=["app"], files=["app.py"])
    result = diff(trace, static)
    assert result.missing == ["hookfix_extra", "importlib_resources"]


def test_diff_keeps_private_package_with_leading_underscore():
    """A leading underscore is part of the name, not noise.

    Regression: ``_is_noise`` dropped every ``_``-prefixed module, so a real
    private package loaded dynamically (``_mylib._core``) was silently omitted
    from the report and the frozen app died. Underscore *stdlib* modules are
    still excluded -- by name, not by prefix.
    """
    trace = TraceResult(
        modules=["_priv", "_priv._core", "_weakrefset"],
        origins={
            "_priv": "/x/_priv/__init__.py",
            "_priv._core": "/x/_priv/_core.py",
            "_weakrefset": "/usr/lib/python3.13/_weakrefset.py",
        },
    )
    static = StaticResult(imports=["_priv"], reachable=["app", "_priv"], files=["app.py"])
    result = diff(trace, static)
    assert result.missing == ["_priv._core"]
    assert "_weakrefset" in result.stdlib_only


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
    trace = TraceResult(
        modules=["dynpkg", "dynpkg.helper"],
        origins={"dynpkg": "/x/dynpkg/__init__.py", "dynpkg.helper": "/x/dynpkg/helper.py"},
    )
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


def test_diff_reports_unresolved_import_separately():
    """An import nothing could resolve is not a hidden import.

    Regression: the tracer records attempted-but-unresolved names with an empty
    origin, and they were reported as hidden imports. There is no file to
    bundle, so ``--hidden-import`` cannot help.
    """
    trace = TraceResult(modules=["requests", "not_installed"], origins={"requests": "/x/r.py"})
    static = StaticResult(imports=[], reachable=["app"], files=[])
    result = diff(trace, static)
    assert result.missing == ["requests"]
    assert result.unresolved == ["not_installed"]


def test_diff_rejects_scan_without_entry_point():
    trace = TraceResult(modules=["requests"])
    static = StaticResult(imports=[], files=[])
    with pytest.raises(ValueError, match="reachable set"):
        diff(trace, static)
