# hookfix

**Find the hidden imports that break your frozen Python app.**

[![CI](https://github.com/sqmyou/hookfix/actions/workflows/ci.yml/badge.svg)](https://github.com/sqmyou/hookfix/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/hookfix.svg?style=flat)](https://pypi.org/project/hookfix/)
[![Python versions](https://img.shields.io/pypi/pyversions/hookfix.svg?style=flat)](https://pypi.org/project/hookfix/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

You build your app, it works perfectly. You freeze it with PyInstaller or
Nuitka, ship the binary, and it dies on a user's machine with:

```
ModuleNotFoundError: No module named 'your_plugin'
```

The module is installed. It is in your source tree. It just never appears in an
`import` statement that a static analyser can see — it is pulled in by
`importlib.import_module`, a plugin registry, an entry point, or a
`__getattr__` on a package. Freezers trace imports by reading source, so they
miss it, and you get to add `--hidden-import` flags one error report at a time.

`hookfix` takes the other route. It **runs** your program, watches every module
the interpreter actually imports, subtracts the imports that are visible to a
static scan, and hands you the difference — the hidden imports, ready to paste
into your build.

```console
$ hookfix run app.py --path .

hookfix report
==============

script        /home/you/app/app.py
python        3.12.4
exit status   0
scanned       12 files, 34 static imports
observed      87 modules imported at runtime

Hidden imports (2)
------------------
  plugins.report
  yaml

These modules were imported at runtime but are invisible to a static scan.
Add them to your build:

  pyinstaller --hidden-import=plugins.report --hidden-import=yaml ...

Or generate a hook file for all of them at once:

  hookfix fix

(That only works for modules PyInstaller actually processes. See
[`hookfix fix`](#hookfix-fix--generate-build-configuration) for the details.)

Dynamic import sites (2)
------------------------
  app.py:41:12         importlib.import_module
  plugins/load.py:9:5  __import__

These call sites are why the imports above are invisible to static analysis.
```

## Why not just use audit hooks?

The obvious way to watch imports is a CPython audit hook
([PEP 578](https://peps.python.org/pep-0578/)) listening for the `import`
event. It does not work, and the reason is subtle enough to be worth stating:

```python
import importlib
importlib.import_module("plugins.report")   # does NOT raise the import event
__import__("plugins.report")                # raises it
import plugins.report                       # raises it
```

`importlib.import_module` calls the internal `_gcd_import` directly and never
raises the audit event. Since `importlib.import_module` is *the* standard way to
load a module dynamically, an audit-hook-based tracer has a blind spot over
precisely the case it is meant to catch.

`hookfix` installs an `importlib.abc.MetaPathFinder` at the front of
`sys.meta_path` instead. Every module resolution that goes through the import
system passes through `sys.meta_path`, whatever triggered it — so statements,
`importlib`, `__import__` and lazy loaders are all observed.

## Installation

```console
pip install hookfix
```

`hookfix` has no runtime dependencies and needs Python 3.10 or newer.

## Usage

### `hookfix run` — trace a program

```console
hookfix run app.py --path .
```

Runs `app.py` under the tracer and prints the report above. `--path` sets the
directory to scan statically (default: the script's directory). Arguments after
`--` are passed through to your program:

```console
hookfix run app.py -- --config prod.yaml
```

Useful flags:

| Flag | Meaning |
| --- | --- |
| `--path DIR` | directory to scan statically (default: the script's directory) |
| `--exclude NAME` | skip a directory or module while scanning (repeatable) |
| `--trace-out FILE` | save the trace as JSON for later use |
| `--json` | print the report as JSON instead of text |
| `--quiet` | suppress the traced program's own output |

### `hookfix diff` — compare a saved trace against source

```console
hookfix run app.py --trace-out trace.json --quiet
hookfix diff trace.json --path .
```

Re-runs the comparison without executing the program again. Handy in CI, where
you want to trace once and check the result from a different step.

### `hookfix fix` — generate build configuration

```console
hookfix fix trace.json                        # -> hook-<package>.py on stdout
hookfix fix trace.json -o hooks/              # -> hooks/hook-<package>.py
hookfix fix trace.json --module reporters     # -> hook-reporters.py (explicit name)
hookfix fix trace.json --spec                 # -> hiddenimports = [...] snippet
hookfix fix trace.json --nuitka               # -> --include-module=... flags
```

`--spec` prints just the `hiddenimports = [...]` list to drop into an existing
`.spec` file, or to pass as `--hidden-import` flags. It always works.

`--nuitka` prints one `--include-module=NAME` flag per hidden import, ready to
append to a Nuitka build command:

```console
$ hookfix fix trace.json --nuitka
# Generated by hookfix. https://github.com/sqmyou/hookfix
#
# Add these flags to your Nuitka build command. Each --include-module
# forces one module into the build unconditionally, so none of them relies
# on Nuitka reading an import it cannot see. Review the list first: it
# reflects one execution of the program.
--include-module=reporters.json_reporter
```

A Nuitka build has no equivalent of the PyInstaller hook constraint below:
`--include-module` is unconditional, so it covers a module nothing imports just
as reliably as one that is. The flags are therefore the whole list, always.

> **The hook-file and `.spec` output is PyInstaller-specific.** `run` and `diff`
> are freezer-agnostic: the list they report is exactly the set of modules
> missing from the build. `fix --nuitka` renders that list for Nuitka;
> `fix` on its own, and `fix --spec`, render it for PyInstaller.

The hook file is the reusable form of `--hidden-import`, but it comes with a
constraint worth understanding, because it is the difference between a build
that works and one that fails silently:

> PyInstaller reads `hook-NAME.py` only while it is processing a module called
> `NAME`. A hook named after the entry script is never read — PyInstaller knows
> the entry script as `__main__`, not by its file name.

So a hook can only carry imports for a module PyInstaller already imports. The
hidden imports are submodules (`reporters.json_reporter`), so `hookfix` keys the
hook to the top-level package that owns them (`reporters`). That works when your
program imports the package: PyInstaller processes `reporters`, reads
`hook-reporters.py`, and picks up the submodule.

It cannot work when *nothing* imports the package — which is precisely why the
submodule was invisible in the first place. In that case `hookfix` writes no
hook file and tells you to use `--hidden-import` instead, because a hook it
wrote would be dead code:

```console
$ hookfix fix trace.json
no hook file written: none of the hidden imports are modules PyInstaller
processes, so a hook would never fire.

1 module(s) cannot be covered by a hook (nothing imports them, so PyInstaller
never processes them). Pass these instead:

  pyinstaller --hidden-import=reporters.json_reporter ...
```

`--module NAME` overrides the name. It refuses a name that matches the entry
script, since that hook would never be read.

## What it does and does not do

**It reports what one run actually imported.** That is the honest boundary of
any runtime tool. If a code path never executed — a plugin for a mode you did
not exercise, a platform-specific branch — its imports will not appear.

**Child processes are not traced, but their spawn sites are named.** The tracer
sees only the interpreter it runs in. If your program spawns another Python
process (`subprocess`, `multiprocessing`) and that child does dynamic imports,
those imports are not in the report. An audit hook observes the spawn itself, so
the report names the exact line that started the child:

```
Child processes were started
----------------------------
  app.py:12  subprocess.Popen
```

Point `hookfix run` at the child entry point named there to see its imports. A
program that merely imports `subprocess` without spawning gets a weaker
*Child processes may have been used* notice, since the import alone is only a
hint.

**A moved trace needs `--entry`.** A trace records the entry-point path from the
machine it was taken on, so re-scanning it from a different checkout fails with
`entry point does not exist`. Pass `--entry path/to/app.py` to `diff` or `fix`
to point at the entry script here.

So: run `hookfix` against the widest set of inputs you can, ideally the same
ones your smoke tests use. The output tells you which call sites are dynamic, so
you can see what you might have missed. Treat the generated hook file as a
starting point to review, not as a finished artefact — the header says as much.

Imports that nothing could resolve are listed separately, under *Unresolved
imports*. They are not build settings: there is no file to bundle, so the fix is
to install the module (or accept that it is built in and always available).

It also cannot tell you about data files, native libraries, or metadata that a
freezer might drop. It is specifically about imports.

## How it works

1. **Trace.** The CLI spawns a child process (`python -m hookfix._bootstrap`)
   that installs a recording meta path finder and then runs your script with
   `runpy`, mimicking a plain `python script.py` invocation — or
   `python -m package`, when the entry point is a package's `__main__.py`.
   Every resolved module is logged as `name<TAB>origin`, and a module that
   resolves without a file (a namespace package) logs its search location. A
   second, audit-hook recorder logs any process-spawn event with the user-code
   line that raised it.

2. **Scan.** `hookfix` walks the source tree with `ast`, collects every
   `import` statement, and records the location of every dynamic import call
   site. From the entry point it then walks the import graph to work out which
   modules a freezer will actually bundle. The two sets differ: a file that
   nothing imports is still scanned but is never bundled, so comparing against
   every import in the tree would hide real gaps.

3. **Diff.** The runtime modules minus the reachable ones are the hidden
   imports. Standard-library modules are split out (a freezer bundles those
   anyway), import-machinery internals are filtered as noise, and names that
   resolved to no file are reported as unresolved rather than hidden.

4. **Report.** The remainder is printed, or rendered as a hook file or spec
   snippet.

Everything is serialisable: `--trace-out` writes a versioned JSON document, and
`diff`/`fix` read it back, so a trace taken on one machine can be inspected on
another.

## Development

```console
git clone https://github.com/sqmyou/hookfix
cd hookfix
python -m pip install -e ".[dev]"
python -m pytest
```

The test suite includes a fixture (`tests/fixtures/dynamic_app`) that loads a
plugin through `importlib.import_module` — the case that motivated the whole
tool. `python -m ruff check src tests` and `python -m mypy` must both pass.

## License

MIT. See [LICENSE](LICENSE).
