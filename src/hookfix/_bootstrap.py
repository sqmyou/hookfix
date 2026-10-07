"""Entry point for the tracer subprocess.

Invoked by the CLI as::

    python -m hookfix._bootstrap <logfile> <script> [args...]

It installs the recording meta path finder, writes one ``module<TAB>origin``
line per import to ``logfile``, then hands control to the user's script with
:func:`runpy.run_path` so the script sees ``__name__ == "__main__"`` exactly as
it would under a plain ``python script.py`` invocation.

This module is deliberately self-contained: the child process must not import
the rest of hookfix before the tracer is installed, or those imports would be
recorded as if the user's program had made them.
"""

from __future__ import annotations

import os
import runpy
import sys
from typing import Any


class _Recorder:
    """Minimal meta path finder that logs every resolved module."""

    def __init__(self, log: Any) -> None:
        self._log = log

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
                origin = getattr(spec, "origin", None)
                if not origin:
                    # A namespace package (PEP 420) has no ``__init__.py`` and so
                    # no origin. Its search locations stand in, so that a
                    # resolved namespace package is not mistaken for a missing
                    # one.
                    locations = getattr(spec, "submodule_search_locations", None)
                    if locations:
                        origin = next(iter(locations), None)
                self._log.write(f"{fullname}\t{origin or ''}\n")
                return spec
        self._log.write(f"{fullname}\t\n")
        return None


def _package_of(script: str) -> str | None:
    """Return the package name when ``script`` is a ``__main__.py`` of a package.

    ``python -m mypkg`` runs ``mypkg/__main__.py``; the module to execute is the
    package, and the directory that must be on ``sys.path`` is the package's
    *parent*, not the package itself.
    """
    if os.path.basename(script) != "__main__.py":
        return None
    pkg_dir = os.path.dirname(os.path.abspath(script))
    if not os.path.exists(os.path.join(pkg_dir, "__init__.py")):
        return None
    return os.path.basename(pkg_dir)


def _main() -> None:  # pragma: no cover - exercised via subprocess in tests
    if len(sys.argv) < 3:
        print("usage: python -m hookfix._bootstrap <logfile> <script> [args...]", file=sys.stderr)
        raise SystemExit(2)

    logfile = sys.argv[1]
    script = sys.argv[2]

    # Mimic a plain ``python script.py`` invocation: the script's directory
    # becomes the first entry on sys.path, so sibling packages resolve. For a
    # package entry point the package's parent is what belongs on sys.path.
    package = _package_of(script)
    if package is not None:
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(script))))
    else:
        sys.path.insert(0, os.path.dirname(os.path.abspath(script)))

    # Present the script the way a normal ``python script.py`` invocation does.
    sys.argv = [script, *sys.argv[3:]]

    with open(logfile, "w", encoding="utf-8", buffering=1) as log:
        # Install the recorder last, so nothing hookfix itself imported is
        # logged as if the user's program had imported it.
        sys.meta_path.insert(0, _Recorder(log))
        if package is not None:
            runpy.run_module(package, run_name="__main__", alter_sys=True)
        else:
            runpy.run_path(script, run_name="__main__")


if __name__ == "__main__":  # pragma: no cover
    _main()
