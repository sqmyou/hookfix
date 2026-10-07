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
- `src/hookfix/scanner.py` — `ast`-based static scan; also computes the set of
  modules reachable from the entry point.
- `src/hookfix/differ.py` — runtime trace minus the reachable imports.
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

5. **Subtract the *reachable* set, never the whole tree.** `StaticResult` carries
   two sets and they are not interchangeable. `imports` is everything the
   scanner read anywhere; `reachable` is what a freezer can actually reach from
   the entry point. Comparing a trace against `imports` treats a module inside a
   dynamically loaded package as already covered, which is exactly the bug
   fixed in 0.1.1 — hookfix's own advice produced a binary that crashed. `diff`
   raises rather than fall back to `imports`.

6. **A hook file only fires for a module PyInstaller processes.** PyInstaller
   reads `hook-NAME.py` while processing a module called `NAME`. The entry
   script is never imported as a module — PyInstaller knows it as `__main__` —
   so a hook named after the script file is silently dead. Key hooks to the
   top-level package that owns the hidden imports (`hook-reporters.py`). If
   nothing imports that package, no hook can cover its submodules: emit
   `--hidden-import` instead. `hook_targets()` and `_cmd_fix` enforce this.

7. **A name with no origin is not a hidden import.** The tracer records an
   import it attempted but could not resolve with an empty origin. There is no
   file to bundle, so `--hidden-import` cannot help; `diff` reports these under
   `unresolved`. Namespace packages resolve without a file, so the tracer logs
   their search location instead of leaving the origin empty.

8. **Keep PyInstaller in the dev extras.** The freeze integration test is
   skipped without it, and a skipped test is how the dead hook file shipped in
   the first place. CI installs `.[dev]` and must actually run the freeze.

9. **A leading underscore is not noise.** `_mylib._core` is a real private
   package. Filter only `importlib`, hookfix's own modules, and stdlib/built-in
   names — the latter by name, not by prefix, since `_csv` and `_sre` are
   stdlib but `_priv` is not. A prefix rule here silently hides real gaps.

## Releasing

`main` is the release branch. To cut a release:

1. Bump `__version__` in `src/hookfix/__init__.py` (hatchling reads it from
   there) and add a dated section to `CHANGELOG.md`.
2. `python -m build && python -m twine check dist/*` — both must pass.
3. Commit, push, then `git tag -a vX.Y.Z -m "..." && git push origin vX.Y.Z`.
4. `gh release create vX.Y.Z --title ... --notes ...` — publishing the release
   triggers `.github/workflows/publish.yml`, which builds and uploads to PyPI.

Publishing uses PyPI Trusted Publishing (OIDC), so no API token is stored here.
This requires a one-time setup on PyPI that only a human can do: at
<https://pypi.org/manage/account/publishing/>, add a pending publisher with

- PyPI project name: `hookfix`
- Owner: `sqmyou`
- Repository: `hookfix`
- Workflow name: `publish.yml`
- Environment: `pypi`

Until that exists, the `publish` job fails with `invalid-publisher`. The
`build` job still succeeds, so the artefacts can be checked without PyPI.

