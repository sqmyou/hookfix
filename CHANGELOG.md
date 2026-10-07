# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
