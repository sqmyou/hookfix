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
