"""Entry point that loads a package by name at runtime.

The package it loads, ``dynpkg``, statically imports one of its own submodules
from ``__init__.py``. Nothing imports ``dynpkg`` statically, so a freezer never
walks into that file and never learns about the submodule -- which is exactly
the case a whole-tree static scan gets wrong.
"""

import importlib
import sys


def main() -> int:
    name = sys.argv[1] if len(sys.argv) > 1 else "dynpkg"
    module = importlib.import_module(name)
    print(f"loaded {module.NAME}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
