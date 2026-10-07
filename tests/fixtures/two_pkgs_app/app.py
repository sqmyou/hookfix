"""Two packages, each with a submodule reachable only at runtime.

PyInstaller processes both ``alpha`` and ``beta`` (they are named in import
statements), so ``hookfix fix`` should write one hook for each -- and each hook
must carry only its own package's modules, not the union.
"""

import importlib

import alpha  # noqa: F401
import beta  # noqa: F401

print("alpha:", importlib.import_module("alpha.one").VALUE)
print("beta:", importlib.import_module("beta.two").VALUE)
