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
                origin = getattr(spec, "origin", None) or ""
                self._log.write(f"{fullname}\t{origin}\n")
                return spec
        self._log.write(f"{fullname}\t\n")
        return None


def _main() -> None:  # pragma: no cover - exercised via subprocess in tests
    if len(sys.argv) < 3:
        print("usage: python -m hookfix._bootstrap <logfile> <script> [args...]", file=sys.stderr)
        raise SystemExit(2)

    logfile = sys.argv[1]
    script = sys.argv[2]

    # Mimic a plain ``python script.py`` invocation: the script's directory
    # becomes the first entry on sys.path, so sibling packages resolve.
    script_dir = os.path.dirname(os.path.abspath(script))
    sys.path.insert(0, script_dir)

    # Present the script the way a normal ``python script.py`` invocation does.
    sys.argv = [script, *sys.argv[3:]]

    with open(logfile, "w", encoding="utf-8", buffering=1) as log:
        # Install the recorder last, so nothing hookfix itself imported is
        # logged as if the user's program had imported it.
        sys.meta_path.insert(0, _Recorder(log))
        runpy.run_path(script, run_name="__main__")


if __name__ == "__main__":  # pragma: no cover
    _main()
