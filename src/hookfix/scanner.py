"""Static analysis of a source tree.

This module reproduces the part of the problem freezers already solve: reading
``import`` statements out of source files. hookfix needs it so that it can
subtract the statically visible imports from the runtime trace and leave only
the imports the build is actually missing.

Two different sets come out of a scan, and the distinction is the whole point:

``imports``
    Every module referenced by an ``import`` statement *anywhere* in the tree.
    A file that nothing imports is still scanned, so this set is larger than
    what a freezer ships. Comparing a runtime trace against it silently drops
    modules that are genuinely missing.

``reachable``
    The modules a freezer will actually bundle: those reachable from the entry
    point by following ``import`` statements, plus the parents of each. This is
    what a runtime trace must be compared against.

We parse with :mod:`ast` rather than regular expressions so that imports inside
functions, conditionals and ``try`` blocks are all found, and so that the
location of every dynamic import call can be reported precisely.
"""

from __future__ import annotations

import ast
import os
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from .errors import ScanError
from .model import DynamicSite, StaticResult

#: Functions that import a module from a string. ``importlib.import_module``
#: and ``__import__`` are the common ones; ``exec``/``eval`` can execute an
#: import statement assembled at runtime.
_DYNAMIC_CALLS = {
    ("importlib", "import_module"),
    ("__import__", None),
    ("builtins", "__import__"),
}

_EXEC_CALLS = {"exec", "eval"}

_DEFAULT_EXCLUDES = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "env",
    "build",
    "dist",
    "__pycache__",
    "node_modules",
    ".tox",
    ".nox",
    ".mypy_cache",
    ".ruff_cache",
    ".pytest_cache",
    ".hookfix",
}


@dataclass
class _FileInfo:
    """What one scanned file contributes to the import graph."""

    #: The module name this file defines (``pkg.mod``, or ``pkg`` for an
    #: ``__init__.py``).
    modname: str
    #: The package the file belongs to (``pkg.mod`` -> ``pkg``; ``pkg`` for an
    #: ``__init__.py``; ``""`` for a top-level module). Relative imports are
    #: resolved against this.
    package: str
    #: Absolute module names this file imports, relative imports already
    #: resolved. These are the edges the reachability walk follows.
    edges: list[str] = field(default_factory=list)


def _iter_python_files(root: Path, excludes: set[str]) -> Iterable[Path]:
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in excludes and not d.startswith("."))
        for filename in sorted(filenames):
            if filename.endswith(".py"):
                yield Path(dirpath) / filename


def _call_name(node: ast.Call) -> list[str]:
    """Return the dotted components of a call target, e.g. ``["importlib", "import_module"]``."""
    func = node.func
    parts: list[str] = []
    while isinstance(func, ast.Attribute):
        parts.append(func.attr)
        func = func.value
    if isinstance(func, ast.Name):
        parts.append(func.id)
        return list(reversed(parts))
    return []


def _literal_arg(node: ast.Call) -> str | None:
    if not node.args:
        return None
    first = node.args[0]
    if isinstance(first, ast.Constant) and isinstance(first.value, str):
        return first.value
    return None


def _resolve_relative(package: str, level: int, module: str | None) -> str:
    """Resolve ``from . import x`` against the package containing the file.

    ``level`` counts dots: 1 is the file's own package, 2 its parent, and so
    on. A relative import that climbs above the top of the tree cannot be
    resolved and yields ``""``.
    """
    parts = package.split(".") if package else []
    climb = level - 1
    if climb:
        if climb > len(parts):
            return ""
        parts = parts[: len(parts) - climb]
    if module:
        parts = [*parts, *module.split(".")]
    return ".".join(parts)


def _scan_tree(
    tree: ast.AST, relpath: str, package: str
) -> tuple[set[str], list[DynamicSite], set[str]]:
    """Return ``(imports, sites, edges)`` for one parsed file.

    ``imports`` is what the file references, as written (this is what the
    report shows). ``edges`` is the same set with relative imports resolved to
    absolute names, which is what the reachability walk needs.
    """
    imports: set[str] = set()
    sites: list[DynamicSite] = []
    edges: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                # Keep the fully-qualified name: ``import a.b`` tells a freezer
                # about ``a.b``, and the differ compares full names.
                imports.add(alias.name)
                edges.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                base = node.module
            else:
                base = _resolve_relative(package, node.level, node.module)
                if base:
                    # ``from . import x`` never names a third-party dependency,
                    # so it is not reported, but it is still a real edge.
                    edges.add(base)
            if not base:
                continue
            if node.level == 0:
                imports.add(base)
            for alias in node.names:
                if alias.name == "*":
                    continue
                imports.add(f"{base}.{alias.name}")
                edges.add(f"{base}.{alias.name}")
        elif isinstance(node, ast.Call):
            parts = _call_name(node)
            if not parts:
                continue
            dotted = tuple(parts[-2:]) if len(parts) >= 2 else (parts[0], None)
            simple = parts[-1]
            if dotted in _DYNAMIC_CALLS or (simple == "__import__" and len(parts) == 1):
                sites.append(
                    DynamicSite(
                        path=relpath,
                        lineno=node.lineno,
                        col=node.col_offset,
                        kind=".".join(parts),
                        target=_literal_arg(node),
                    )
                )
            elif simple in _EXEC_CALLS:
                sites.append(
                    DynamicSite(
                        path=relpath,
                        lineno=node.lineno,
                        col=node.col_offset,
                        kind=simple,
                        target=_literal_arg(node),
                    )
                )

    return imports, sites, edges


def _parse_file(path: Path, relpath: str) -> tuple[ast.AST, _FileInfo] | None:
    """Parse one file, returning its AST and graph contribution, or ``None``."""
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        # A file we cannot parse is not a reason to fail the whole scan;
        # a freezer would report it separately.
        return None

    parts = Path(relpath).parts
    if parts[-1] == "__init__.py":
        modname = ".".join(parts[:-1])
        package = modname
    else:
        stem = parts[-1][: -len(".py")]
        modname = ".".join([*parts[:-1], stem])
        package = ".".join(parts[:-1])
    _, _, edges = _scan_tree(tree, relpath, package)
    return tree, _FileInfo(modname=modname, package=package, edges=sorted(edges))


def _with_parents(names: Iterable[str]) -> set[str]:
    """Add every parent package of every name: importing ``a.b.c`` runs ``a`` and ``a.b``."""
    out: set[str] = set()
    for name in names:
        out.add(name)
        parts = name.split(".")
        for i in range(1, len(parts)):
            out.add(".".join(parts[:i]))
    return out


def _reachable_from(entry: Path, relpath: str, module_files: dict[str, _FileInfo]) -> set[str]:
    """Walk the static import graph from the entry point.

    ``entry`` is parsed directly, so an entry point that lives outside the
    scanned tree still contributes its own imports.
    """
    parsed = _parse_file(entry, relpath)
    if parsed is None:
        raise ScanError(f"cannot parse entry point: {entry}")
    _, entry_info = parsed

    seen: set[str] = {entry_info.modname}
    queue: list[str] = [entry_info.modname, *entry_info.edges]
    while queue:
        name = queue.pop()
        if name in seen:
            continue
        seen.add(name)
        info = module_files.get(name)
        if info is not None:
            queue.extend(info.edges)

    return _with_parents(seen)


def scan(
    root: os.PathLike[str] | str,
    excludes: Iterable[str] = (),
    entry: os.PathLike[str] | str | None = None,
) -> StaticResult:
    """Scan ``root`` for import statements and dynamic import call sites.

    When ``entry`` is given, also compute which modules a freezer would bundle
    by following imports from that entry point (``StaticResult.reachable``).
    """
    root_path = Path(root).resolve()
    if not root_path.exists():
        raise ScanError(f"path does not exist: {root_path}")

    exclude_set = set(_DEFAULT_EXCLUDES) | set(excludes)
    all_imports: set[str] = set()
    all_sites: list[DynamicSite] = []
    scanned: list[str] = []
    module_files: dict[str, _FileInfo] = {}

    for path in _iter_python_files(root_path, exclude_set):
        relpath = str(path.relative_to(root_path))
        parsed = _parse_file(path, relpath)
        if parsed is None:
            continue
        tree, info = parsed
        imports, sites, _ = _scan_tree(tree, relpath, info.package)
        all_imports |= imports
        all_sites.extend(sites)
        scanned.append(relpath)
        module_files.setdefault(info.modname, info)

    reachable: list[str] = []
    entry_str: str | None = None
    if entry is not None:
        entry_path = Path(entry).resolve()
        if not entry_path.exists():
            raise ScanError(f"entry point does not exist: {entry_path}")
        entry_str = str(entry_path)
        try:
            entry_rel = str(entry_path.relative_to(root_path))
        except ValueError:
            # Entry outside the scanned tree: still use it for its own imports.
            entry_rel = entry_path.name
        reachable = sorted(_reachable_from(entry_path, entry_rel, module_files))

    return StaticResult(
        imports=sorted(all_imports),
        reachable=reachable,
        entry=entry_str,
        dynamic_sites=all_sites,
        files=scanned,
    )
