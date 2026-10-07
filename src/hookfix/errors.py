"""Exceptions raised by hookfix."""

from __future__ import annotations


class HookfixError(Exception):
    """Base class for every error hookfix raises deliberately.

    The CLI catches this and prints the message without a traceback, so
    user-facing failures stay readable.
    """


class TraceError(HookfixError):
    """The traced program could not be run or its trace could not be collected."""


class ScanError(HookfixError):
    """The static scan could not complete."""
