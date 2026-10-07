"""Entry point for ``python -m mypkg``."""

import importlib

mod = importlib.import_module("mypkg.worker")
print("worker:", mod.NAME)
