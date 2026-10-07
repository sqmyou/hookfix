"""App whose dynamically loaded submodule lives in a statically imported package.

``dynpkg`` is named in a plain import statement, so PyInstaller processes it and
will read ``hook-dynpkg.py``. The ``helper`` submodule is only reached through
``importlib.import_module``, so a static scan misses it.
"""

import importlib

import dynpkg  # noqa: F401

mod = importlib.import_module("dynpkg.helper")
print("helper:", mod.VALUE)
