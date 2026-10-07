"""Entry point for the dynamic-import fixture.

This script models the way real applications lose modules at freeze time: the
plugin name is assembled at runtime, so no source scanner can tell which
module will be imported. ``csv`` is imported normally and should therefore show
up in a static scan; ``plugins.report`` is not visible anywhere in the source.
"""

import csv
import importlib
import sys

# A plugin registry, exactly the pattern that defeats static analysis.
REGISTRY = {
    "report": "plugins.report",
    "archive": "plugins.archive",
}


def load(plugin: str):
    return importlib.import_module(REGISTRY[plugin])


def main(argv):
    which = argv[1] if len(argv) > 1 else "report"
    module = load(which)
    # Touch the statically-visible import so it is genuinely used.
    _ = csv.field_size_limit()
    print(f"{which}: {module.describe()}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
