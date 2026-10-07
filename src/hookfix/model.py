"""Shared data model for hookfix results.

The types here are deliberately plain dataclasses with ``to_dict``/``from_dict``
so that a trace or report can be serialised to JSON, committed as a CI artifact,
and re-read later on a different machine.
"""

from __future__ import annotations

import sys
from dataclasses import asdict, dataclass, field
from typing import Any

#: Schema version for the JSON artefacts we write. Bump when the shape changes
#: in a way that older readers cannot understand.
SCHEMA_VERSION = 1


@dataclass
class DynamicSite:
    """A call site in the source that imports a module at runtime.

    These are the places static analysis is blind to. Recording them lets the
    report point at the exact line responsible for a module that only appears
    at runtime.
    """

    path: str
    lineno: int
    col: int
    #: ``importlib.import_module``, ``__import__``, ``exec`` or ``eval``.
    kind: str
    #: The literal argument, when it could be resolved statically.
    target: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DynamicSite:
        return cls(**data)


@dataclass
class StaticResult:
    """What a static scan of the source tree can see."""

    #: Top-level module names referenced by ``import`` statements.
    imports: list[str] = field(default_factory=list)
    #: Locations of dynamic import calls.
    dynamic_sites: list[DynamicSite] = field(default_factory=list)
    #: Files that were scanned.
    files: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "imports": self.imports,
            "dynamic_sites": [site.to_dict() for site in self.dynamic_sites],
            "files": self.files,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StaticResult:
        return cls(
            imports=list(data.get("imports", [])),
            dynamic_sites=[DynamicSite.from_dict(d) for d in data.get("dynamic_sites", [])],
            files=list(data.get("files", [])),
        )


@dataclass
class TraceResult:
    """What actually happened when the program ran."""

    #: Every fully-qualified module name the interpreter imported.
    modules: list[str] = field(default_factory=list)
    #: ``name -> file`` for modules that reported a filesystem origin.
    origins: dict[str, str] = field(default_factory=dict)
    #: Interpreter version the trace was taken under.
    python: str = field(default_factory=lambda: sys.version.split()[0])
    #: Exit status of the traced program.
    returncode: int = 0

    @property
    def top_level(self) -> list[str]:
        """Top-level names only (``a.b.c`` collapses to ``a``), sorted."""
        return sorted({name.split(".")[0] for name in self.modules})

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "python": self.python,
            "returncode": self.returncode,
            "modules": self.modules,
            "origins": self.origins,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TraceResult:
        return cls(
            modules=list(data.get("modules", [])),
            origins=dict(data.get("origins", {})),
            python=data.get("python", ""),
            returncode=int(data.get("returncode", 0)),
        )


@dataclass
class DiffResult:
    """Modules imported at runtime that static analysis could not see."""

    #: Top-level names present at runtime but absent from the static scan.
    missing: list[str] = field(default_factory=list)
    #: Runtime-only names that live in the standard library. Informational:
    #: a freezer normally bundles these already.
    stdlib_only: list[str] = field(default_factory=list)
    #: Names seen by both, for context.
    common: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "missing": self.missing,
            "stdlib_only": self.stdlib_only,
            "common": self.common,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DiffResult:
        return cls(
            missing=list(data.get("missing", [])),
            stdlib_only=list(data.get("stdlib_only", [])),
            common=list(data.get("common", [])),
        )
