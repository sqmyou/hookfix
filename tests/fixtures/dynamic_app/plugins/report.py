"""A plugin that is only ever reached through ``importlib``."""


def describe() -> str:
    return "report plugin"
