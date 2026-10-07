"""Runtime import tracer.

The tracer works by installing a :class:`importlib.abc.MetaPathFinder` at the
front of :data:`sys.meta_path`. Every module resolution that goes through the
import system passes through the finders in ``sys.meta_path``, so a finder
placed at the front observes imports that originate from an ``import``
statement, from :func:`importlib.import_module`, from :func:`__import__`, and
from lazy ``__getattr__`` loaders alike.

Why not CPython audit hooks? The ``import`` audit event is raised only on the
``import`` statement / ``__import__`` path. :func:`importlib.import_module`
calls the internal ``_gcd_import`` directly and never raises it, which is
precisely the dynamic case that breaks frozen builds. A meta path finder has no
such blind spot.

The finder records each module name the first time it is resolved, together
with the file it came from. Modules already present in :data:`sys.modules`
before the tracer is installed are not seen, so the tracer must be installed
before the program under test runs.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from typing import Any

from .errors import TraceError


class ImportTracer:
    """Record module imports performed by the running interpreter."""

    def __init__(self) -> None:
        self.modules: set[str] = set()
        self.origins: dict[str, str] = {}
        self._installed = False

    def install(self) -> None:
        """Insert the recording finder at the front of ``sys.meta_path``."""
        if self._installed:
            raise TraceError("ImportTracer.install() may only be called once")
        if not hasattr(sys, "meta_path"):
            raise TraceError("this interpreter does not provide sys.meta_path")
        sys.meta_path.insert(0, _RecordingFinder(self))
        self._installed = True

    def record(self, name: str, origin: str | None) -> None:
        self.modules.add(name)
        if origin and name not in self.origins:
            self.origins[name] = origin


class _RecordingFinder:
    """A meta path finder that records names and delegates to the real finders.

    It must reproduce the search the interpreter would otherwise perform, so it
    walks the remaining ``sys.meta_path`` entries in order and returns the first
    spec any of them produces. Returning a spec of our own, or delegating to a
    single finder, would break built-in and frozen modules.
    """

    def __init__(self, tracer: ImportTracer) -> None:
        self._tracer = tracer

    def find_spec(
        self,
        fullname: str,
        path: Any | None = None,
        target: Any | None = None,
    ) -> Any:
        for finder in list(sys.meta_path):
            if finder is self:
                continue
            find_spec = getattr(finder, "find_spec", None)
            if find_spec is None:
                continue
            spec = find_spec(fullname, path, target)
            if spec is not None:
                self._tracer.record(fullname, getattr(spec, "origin", None))
                return spec
        # Nothing could resolve it. Record the attempt so that a name which is
        # imported dynamically but absent from the environment is still visible.
        self._tracer.record(fullname, None)
        return None


def traced_run(target: Callable[..., int], *args: Any, **kwargs: Any) -> tuple[ImportTracer, int]:
    """Run ``target`` under a tracer and return ``(tracer, returncode)``."""
    tracer = ImportTracer()
    tracer.install()
    try:
        returncode = target(*args, **kwargs) or 0
    except SystemExit as exc:  # a program is allowed to call sys.exit()
        code = exc.code
        if code is None:
            returncode = 0
        elif isinstance(code, int):
            returncode = code
        else:
            print(code, file=sys.stderr)
            returncode = 1
    return tracer, returncode


def parse_audit_log(text: str) -> tuple[set[str], dict[str, str]]:
    """Parse the line-oriented log written by the subprocess bootstrap.

    Each line is ``module<TAB>origin`` with an empty origin when the import
    machinery did not report a file. This keeps the child process free of any
    dependency on the rest of hookfix.
    """
    modules: set[str] = set()
    origins: dict[str, str] = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        name, _, origin = line.partition("\t")
        name = name.strip()
        if not name:
            continue
        modules.add(name)
        if origin and name not in origins:
            origins[name] = origin
    return modules, origins
