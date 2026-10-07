"""A second plugin, never selected by the default run.

It exists so tests can show that an unexercised code path stays invisible:
hookfix only reports what the traced run actually imported.
"""


def describe() -> str:
    return "archive plugin"
