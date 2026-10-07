"""Shared test helpers."""

from __future__ import annotations

from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"
DYNAMIC_APP = FIXTURES / "dynamic_app"
DYNAMIC_APP_ENTRY = DYNAMIC_APP / "app.py"
#: An app whose dynamically loaded package statically imports a submodule from
#: its ``__init__``. A whole-tree static scan mistakes that submodule for
#: something the freezer already knows about.
NESTED_APP = FIXTURES / "nested_app"
NESTED_APP_ENTRY = NESTED_APP / "app.py"
#: An app whose entry point sits inside the package it belongs to, run as
#: ``python -m mypkg``. The package's own submodule is reached only at runtime.
PKG_APP = FIXTURES / "pkg_app"
PKG_APP_ENTRY = PKG_APP / "mypkg" / "__main__.py"
#: An app whose dynamically loaded submodule lives in a package that *is*
#: statically imported, so a generated hook keyed to that package will fire.
HOOKED_APP = FIXTURES / "hooked_app"
HOOKED_APP_ENTRY = HOOKED_APP / "app.py"
#: Two such packages in one app, to check that each hook carries only its own.
TWO_PKGS_APP = FIXTURES / "two_pkgs_app"
TWO_PKGS_APP_ENTRY = TWO_PKGS_APP / "app.py"
