# AGENTS.md

Repository notes for AI agents and contributors working on hookfix.

## What this project is

`hookfix` finds the imports that break frozen Python apps. It runs a program
under a runtime import tracer, subtracts the imports a static scan can see, and
emits PyInstaller/Nuitka configuration for the difference.

## Commands

```console
python -m pip install -e ".[dev]"     # install with test/lint tools
python -m pytest                      # test suite (28 tests)
python -m ruff check src tests        # lint
python -m mypy                        # strict type check (src/hookfix only)
```

All three must pass before a change is considered done. CI runs them on
Linux (3.10-3.13) plus macOS and Windows (3.12).

## Layout

- `src/hookfix/` — src-layout package. No runtime dependencies; standard
  library only.
- `src/hookfix/tracer.py` — the technical heart. Records imports via a
  `sys.meta_path` finder.
- `src/hookfix/_bootstrap.py` — runs the target script in a child process.
  Deliberately imports nothing from the rest of hookfix, so its own
  dependencies are not mistaken for the user's.
- `src/hookfix/scanner.py` — `ast`-based static scan.
- `src/hookfix/differ.py` — runtime trace minus static imports.
- `src/hookfix/spec_writer.py` — hook file / spec snippet rendering.
- `tests/fixtures/dynamic_app/` — fixture that loads a plugin through
  `importlib.import_module`.
- `examples/demo_app/` — the app used in `DEMO.md`.

## Things worth knowing before you change code

1. **Do not switch the tracer back to CPython audit hooks.**
   `importlib.import_module` calls `_gcd_import` directly and never raises the
   `import` audit event, so audit hooks miss the exact dynamic case this tool
   exists to catch. Verified on Python 3.13. A `sys.meta_path` finder sees
   every path. `README.md` explains this with a runnable example.

2. **Report fully-qualified module names.** PyInstaller needs
   `--hidden-import=reporters.json_reporter`; the bare package name does not
   pull in a submodule that nothing imports statically. This was a real bug,
   caught only by testing against an actual PyInstaller build.

3. **Verify against a real freeze.** The unit tests use a fixture, but the
   bugs that mattered were found by actually building with PyInstaller. If you
   change the differ, scanner or spec writer, freeze `examples/demo_app` and
   confirm the binary runs.

4. **The tool reports one execution.** An unexercised code path stays
   invisible. That is the contract, documented in `README.md` and shown in
   `DEMO.md`. Do not paper over it with guesswork.
