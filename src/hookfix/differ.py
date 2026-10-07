"""Compare a runtime trace against the static import graph."""

from __future__ import annotations

import sys

from .model import DiffResult, StaticResult, TraceResult

#: Modules the interpreter itself provides. They are always available in a
#: frozen build, so a runtime-only standard-library import is not a defect.
_STDLIB = frozenset(getattr(sys, "stdlib_module_names", ()))

#: Built-in extension modules (``_csv``, ``_sre``, ...). Some are absent from
#: ``sys.stdlib_module_names`` on older interpreters, but they are compiled into
#: the interpreter and always present, so they are not a build setting either.
_BUILTIN = frozenset(sys.builtin_module_names)

#: Import-machinery and hookfix modules that appear in every trace and mean
#: nothing to a user reading the report. Matched on the *whole* top-level name:
#: ``importlib._bootstrap`` is noise, ``importlib_resources`` is a real package
#: that merely shares a prefix, and a prefix test hid it.
_INTERNAL_TOP_LEVEL = frozenset({"importlib", "hookfix"})


def _is_noise(name: str) -> bool:
    """Is this a hookfix/import-machinery artefact rather than the user's import?

    Only hookfix's own modules and the import machinery are filtered, and only
    on an exact top-level match. A leading underscore is *not* noise:
    ``_mylib._core`` is a real private package, and dropping it hid a genuine
    hidden import. Neither is a shared prefix: ``importlib_resources`` and a
    hypothetical ``hookfix_extra`` are real packages, so a ``startswith`` test
    silently dropped them from the report. Standard-library and built-in
    underscore modules (``_csv``, ``_sre``, ``_weakrefset``) are still excluded,
    but by name via the stdlib/built-in sets in :func:`diff`.
    """
    if name in {"builtins", "sys", "os", "io", "abc", "codecs", "site", "types", "warnings"}:
        return False
    return name.split(".")[0] in _INTERNAL_TOP_LEVEL


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
        top = name.split(".")[0]
        if _covered_by_reachable(name, reachable):
            common.add(name)
        elif top in stdlib or top in _BUILTIN or name in _BUILTIN:
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
