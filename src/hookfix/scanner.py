"""Static analysis of a source tree.

This module reproduces the part of the problem freezers already solve: reading
``import`` statements out of source files. hookfix needs it so that it can
subtract the statically visible imports from the runtime trace and leave only
the imports the build is actually missing.

We parse with :mod:`ast` rather than regular expressions so that imports inside
functions, conditionals and ``try`` blocks are all found, and so that the
location of every dynamic import call can be reported precisely.
"""

from __future__ import annotations

import ast
import os
from collections.abc import Iterable
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


def _scan_tree(tree: ast.AST, relpath: str) -> tuple[set[str], list[DynamicSite]]:
    imports: set[str] = set()
    sites: list[DynamicSite] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                # Keep the fully-qualified name: ``import a.b`` tells a freezer
                # about ``a.b``, and the differ compares full names.
                imports.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            # ``from . import x`` has module=None and level>0; that is a
            # relative import and never a missing third-party dependency.
            if node.level == 0 and node.module:
                imports.add(node.module)
                for alias in node.names:
                    if alias.name != "*":
                        imports.add(f"{node.module}.{alias.name}")
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

    return imports, sites


def scan(root: os.PathLike[str] | str, excludes: Iterable[str] = ()) -> StaticResult:
    """Scan ``root`` for import statements and dynamic import call sites."""
    root_path = Path(root).resolve()
    if not root_path.exists():
        raise ScanError(f"path does not exist: {root_path}")

    exclude_set = set(_DEFAULT_EXCLUDES) | set(excludes)
    all_imports: set[str] = set()
    all_sites: list[DynamicSite] = []
    scanned: list[str] = []

    for path in _iter_python_files(root_path, exclude_set):
        relpath = str(path.relative_to(root_path))
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        try:
            tree = ast.parse(source, filename=str(path))
        except SyntaxError:
            # A file we cannot parse is not a reason to fail the whole scan;
            # a freezer would report it separately.
            continue
        imports, sites = _scan_tree(tree, relpath)
        all_imports |= imports
        all_sites.extend(sites)
        scanned.append(relpath)

    return StaticResult(
        imports=sorted(all_imports),
        dynamic_sites=all_sites,
        files=scanned,
    )
