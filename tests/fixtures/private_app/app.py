"""A private package (leading underscore) whose submodule loads at runtime."""

import importlib

import _priv  # noqa: F401

print(importlib.import_module("_priv._core").W)
