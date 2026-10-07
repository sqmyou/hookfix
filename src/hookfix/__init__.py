"""hookfix — find the hidden imports that break your frozen Python app.

Freezers such as PyInstaller and Nuitka discover dependencies by reading your
source code. Imports that are constructed at runtime are invisible to that
analysis, so the resulting executable crashes with ``ModuleNotFoundError`` on
the user's machine and not on yours.

hookfix runs your program once under a meta path import tracer, records every
module the interpreter actually imports, and compares that against the imports
a freezer can reach from your entry point. The difference is exactly the set of
modules your build is missing.
"""

__version__ = "0.1.2"

__all__ = ["__version__"]
