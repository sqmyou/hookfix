"""Compare a runtime trace against the static import graph."""

from __future__ import annotations

import sys

from .model import DiffResult, StaticResult, TraceResult

#: Modules the interpreter itself provides. They are always available in a
#: frozen build, so a runtime-only standard-library import is not a defect.
_STDLIB = frozenset(getattr(sys, "stdlib_module_names", ()))

#: Import machinery internals that appear in every trace and mean nothing to a
#: user reading the report.
_INTERNAL_PREFIXES = ("_", "importlib")


def _is_noise(name: str) -> bool:
    if name in {"builtins", "sys", "os", "io", "abc", "codecs", "site", "types", "warnings"}:
        return False
    return name.startswith(_INTERNAL_PREFIXES) or name.startswith("hookfix")


def _stdlib_names() -> set[str]:
    if _STDLIB:
        return set(_STDLIB)
    # Very old interpreters have no ``sys.stdlib_module_names``. Fall back to a
    # conservative empty set: better to over-report than to hide a real gap.
    return set()


def diff(trace: TraceResult, static: StaticResult) -> DiffResult:
    """Return the runtime imports that the static scan did not find.

    ``missing`` holds fully-qualified module names, because that is what a
    freezer needs: ``--hidden-import=reporters.json_reporter``, not the bare
    package name. ``stdlib_only`` is kept separate because a freezer bundles
    the standard library regardless.
    """
    static_names = set(static.imports)
    runtime_names = {name for name in trace.modules if not _is_noise(name)}
    stdlib = _stdlib_names()

    missing: set[str] = set()
    stdlib_only: set[str] = set()
    common: set[str] = set()

    for name in runtime_names:
        if name in static_names:
            common.add(name)
        elif name.split(".")[0] in stdlib:
            stdlib_only.add(name)
        else:
            missing.add(name)

    # A package whose own submodule is reported is redundant: importing the
    # submodule pulls the package in, and listing both clutters the config.
    missing = {name for name in missing if not any(
        other != name and other.startswith(name + ".") for other in missing
    )}

    return DiffResult(
        missing=sorted(missing),
        stdlib_only=sorted(stdlib_only),
        common=sorted(common),
    )
