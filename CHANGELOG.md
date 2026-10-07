# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

[0.1.0]: https://github.com/sqmyou/hookfix/releases/tag/v0.1.0
[Unreleased]: https://github.com/sqmyou/hookfix/compare/v0.1.0...HEAD
