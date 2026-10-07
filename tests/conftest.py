"""Shared test helpers."""

from __future__ import annotations

from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"
DYNAMIC_APP = FIXTURES / "dynamic_app"
DYNAMIC_APP_ENTRY = DYNAMIC_APP / "app.py"
