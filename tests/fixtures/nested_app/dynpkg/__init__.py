"""Loaded by name at runtime, so nothing imports it statically."""

from . import helper

NAME = "dynpkg"
__all__ = ["NAME", "helper"]
