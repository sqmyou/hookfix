"""Demo app: the kind of program that breaks when you freeze it.

Run it directly and it works. Freeze it with PyInstaller and it dies with
``ModuleNotFoundError: No module named 'reporters.json_reporter'``, because the
reporter is selected at runtime and never named in an import statement.

    python examples/demo_app/main.py json
"""

from __future__ import annotations

import importlib
import sys

# The package itself is imported, so PyInstaller sees it and will read a
# generated ``hook-reporters.py``. Which *reporter* runs is still decided at
# runtime, and that module is never named in an import statement -- which is
# exactly what a static scan cannot see.
import reporters  # noqa: F401

# A registry mapping a user-facing name to a module path. Nothing here is a
# literal ``import``, so a static analyser cannot see what will be loaded.
REPORTERS = {
    "json": "reporters.json_reporter",
    "text": "reporters.text_reporter",
}


def load_reporter(name: str):
    module_path = REPORTERS[name]
    return importlib.import_module(module_path)


def main(argv: list[str]) -> int:
    which = argv[1] if len(argv) > 1 else "json"
    reporter = load_reporter(which)
    print(reporter.render({"status": "ok", "items": 3}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
