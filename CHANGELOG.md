# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.2] - 2026-10-07

### Fixed

- **The generated hook file was never loaded.** `hookfix fix --module app`
  wrote `hook-app.py`, and PyInstaller only reads `hook-NAME.py` while it is
  processing a module called `NAME`. The entry script is never imported as a
  module — PyInstaller knows it as `__main__` — so the hook was silently dead
  and the binary still crashed with `ModuleNotFoundError`. The hook is now keyed
  to the top-level package that owns the hidden imports (`hook-reporters.py`),
  which PyInstaller does process, and `--module` refuses a name that matches the
  entry script. Verified against a real PyInstaller build.
- When *nothing* imports the top-level package, no hook can ever fire for its
  submodules — that is precisely why they were invisible. `hookfix fix` now
  writes no hook file in that case and prints the `--hidden-import` flags to use
  instead, rather than emitting an artefact that does nothing.
- **False negative for package entry points.** An app run as `python -m mypkg`
  whose `mypkg/__main__.py` loaded `mypkg.worker` at runtime reported
  `missing: []`, and the frozen binary then died. Two causes: the scanner
  treated a reachable parent package as covering its submodules (so
  `mypkg.worker` looked bundled), and the tracer put the package directory on
  `sys.path`, so the traced program could not even resolve its own package. The
  parent rule is gone and the tracer now handles a package `__main__.py`,
  putting the package's parent on `sys.path` and running it with `runpy`.
- A trace of a program that crashed is incomplete by construction, but
  `hookfix run` printed a clean report and exited 0, so `missing: []` looked
  like a clean bill of health. It now warns on stderr and propagates the exit
  status.

### Changed

- Imports that nothing could resolve are no longer reported as hidden imports.
  The tracer records attempted-but-unresolved names with an empty origin, and
  they were listed as build settings even though there is no file to bundle.
  They now appear under a separate *Unresolved imports* section, which points at
  the environment rather than the build. Namespace packages, which resolve
  without a file, record their search location so they are not mistaken for
  missing.
- The hidden-import list is grouped by top-level package in the report
  (`yaml.*  (17 modules)`), and the copy-paste flags list only the leaves, so a
  package hidden as many submodules no longer buries everything else.

## [0.1.1] - 2026-10-07

### Fixed

- The diff compared a runtime trace against *every* import in the scanned tree,
  but a freezer only bundles what it can reach from the entry point. A module
  imported inside a dynamically loaded package — the case this tool exists for
  — was treated as already covered and dropped from the report, so applying
  hookfix's complete advice still produced a binary that crashed with
  `ModuleNotFoundError`. The scanner now walks the static import graph from the
  entry point (following relative imports and adding parent packages) and the
  diff compares against that set.

### Changed

- The JSON trace format is now schema 2: traces record the entry point that was
  traced. `hookfix diff` and `hookfix fix` reject a schema-1 trace instead of
  guessing which modules are reachable. Re-run `hookfix run --trace-out` to
  regenerate an old trace.

## [0.1.0] - 2026-10-07

First release.

### Added

- `hookfix run <script>` — run a program under a runtime import tracer and
  report the modules it imported that a static scan cannot see.
- `hookfix diff <trace>` — re-compare a saved trace against the source tree.
- `hookfix fix <trace>` — emit a PyInstaller hook file (`hook-<name>.py`) or a
  `hiddenimports = [...]` snippet for an existing `.spec`.
- Static scanner built on `ast`, reporting dynamic import call sites with exact
  line and column numbers.
- Versioned JSON trace format (`--trace-out`) so traces can be saved, inspected
  and re-used across machines and CI steps.
- `py.typed` marker, so downstream type checkers see the package's annotations.

### Notes

- No runtime dependencies; Python 3.10+.
- The tracer records what a single execution imported. A code path that never
  runs stays invisible; see "What it does and does not do" in the README.

[0.1.1]: https://github.com/sqmyou/hookfix/releases/tag/v0.1.1
[0.1.0]: https://github.com/sqmyou/hookfix/releases/tag/v0.1.0
[Unreleased]: https://github.com/sqmyou/hookfix/compare/v0.1.1...HEAD
