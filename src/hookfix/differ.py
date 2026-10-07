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


def _covered_by_reachable(name: str, reachable: set[str]) -> bool:
    """Is ``name`` something the freezer will bundle on its own?

    The comparison is against the modules reachable from the entry point, not
    against every import in the tree. A file that nothing imports is still
    scanned but never bundled, so treating its imports as "already visible"
    would hide modules that are genuinely missing.

    Only an exact match counts. A reachable *parent* does not cover a
    submodule: bundling ``mypkg`` bundles the ``__init__.py`` and what it
    imports, but a ``mypkg.worker`` reached only through
    ``importlib.import_module`` is not in the archive. Treating the parent as
    covering it produced a binary that died with ``ModuleNotFoundError``.
    """
    return name in reachable


def diff(trace: TraceResult, static: StaticResult) -> DiffResult:
    """Return the runtime imports that the static scan did not find.

    ``missing`` holds fully-qualified module names, because that is what a
    freezer needs: ``--hidden-import=reporters.json_reporter``, not the bare
    package name. ``stdlib_only`` is kept separate because a freezer bundles
    the standard library regardless.

    Requires ``static.reachable``. When it is empty the scan had no entry
    point, and there is no honest answer: falling back to the tree-wide
    ``imports`` set would silently drop real gaps, so this is an error.
    """
    reachable = set(static.reachable)
    if not reachable:
        raise ValueError(
            "diff requires a reachable set; scan() was called without an entry point"
        )

    runtime_names = {name for name in trace.modules if not _is_noise(name)}
    stdlib = _stdlib_names()

    missing: set[str] = set()
    stdlib_only: set[str] = set()
    unresolved: set[str] = set()
    common: set[str] = set()

    for name in runtime_names:
        if _covered_by_reachable(name, reachable):
            common.add(name)
        elif name.split(".")[0] in stdlib:
            stdlib_only.add(name)
        elif trace.origins.get(name):
            missing.add(name)
        else:
            # The tracer saw the import attempted but nothing resolved it. There
            # is no file to bundle, so this is not a hidden import: the module is
            # simply absent from the environment (or is built in, in which case
            # it has no origin either). Reporting it as hidden would send the
            # reader chasing a build setting that cannot help.
            unresolved.add(name)

    # A package whose own submodule is reported is redundant: importing the
    # submodule pulls the package in, and listing both clutters the config.
    missing = {name for name in missing if not any(
        other != name and other.startswith(name + ".") for other in missing
    )}
    unresolved = {name for name in unresolved if not any(
        other != name and other.startswith(name + ".") for other in unresolved
    )}

    return DiffResult(
        missing=sorted(missing),
        stdlib_only=sorted(stdlib_only),
        common=sorted(common),
        unresolved=sorted(unresolved),
    )
