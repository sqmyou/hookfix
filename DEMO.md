# Demo: a hidden import, end to end

This is a real transcript, not a mock-up. Every command below was run against
the app in `examples/demo_app`, which selects a reporter at runtime through
`importlib.import_module` — the pattern static analysis cannot see.

The point of the demo is the last step: `hookfix`'s output, applied to an
actual PyInstaller build, turns a crashing binary into a working one.

## The app

```
examples/demo_app/
├── main.py                     # REPORTERS registry + importlib.import_module
└── reporters/
    ├── __init__.py
    ├── json_reporter.py        # never named in an import statement
    └── text_reporter.py
```

`main.py` maps `"json"` to `"reporters.json_reporter"` and loads it by name.
Nothing in the source says `import reporters.json_reporter`, so PyInstaller's
module graph never contains it.

## 1. It works from source

```console
$ python main.py json
{
  "status": "ok",
  "items": 3
}
```

## 2. Freeze it, and it breaks

```console
$ pyinstaller --onedir --name demo_broken --paths . main.py
$ ./dist/demo_broken/demo_broken json
Traceback (most recent call last):
  ...
ModuleNotFoundError: No module named 'reporters.json_reporter'
[PYI-2105:ERROR] Failed to execute script 'main' due to unhandled exception!
```

The classic symptom, and the reason this tool exists. The `reporters` package
itself made it into the bundle — only the reporter chosen at runtime is missing.

## 3. hookfix finds the hidden import

```console
$ hookfix run main.py --path . --quiet --trace-out trace.json

hookfix report
==============

script        /tmp/hookfix_demo/main.py
python        3.13.15
exit status   0
scanned       5 files, 6 static imports
observed      18 modules imported at runtime

Hidden imports (1)
-----------------
  reporters.json_reporter

These modules were imported at runtime but are invisible to a static scan.
Add them to your build:

  pyinstaller --hidden-import=reporters.json_reporter ...

Or generate a hook file for all of them at once:

  hookfix fix

Dynamic import sites (1)
------------------------
  main.py:31:11  importlib.import_module

These call sites are why the imports above are invisible to static analysis.
```

## 4. Generate the build configuration

```console
$ hookfix fix trace.json --path . --spec
hiddenimports = [
    'reporters.json_reporter',
]
```

or a ready-to-use hook file, keyed to the package PyInstaller processes:

```console
$ hookfix fix trace.json --path . -o hooks/
wrote hooks/hook-reporters.py (1 hidden imports)
```

## 5. The frozen binary works

Freeze with only the generated hook applied — no `--hidden-import`:

```console
$ pyinstaller --onedir --name demo_proof --paths . \
      --additional-hooks-dir=hooks main.py
$ ./dist/demo_proof/demo_proof json
{
  "status": "ok",
  "items": 3
}
```

`--additional-hooks-dir=hooks` is the whole difference. Without it the binary
dies with `ModuleNotFoundError`; with it, PyInstaller processes `reporters`,
reads `hook-reporters.py`, and pulls in `reporters.json_reporter`.

Two things make this work, and both matter. The hook is named after
`reporters`, a module PyInstaller processes — a hook named `hook-main.py` would
never be read, because PyInstaller knows the entry script as `__main__`. And the
app imports `reporters` itself, so there is a module for the hook to attach to.

If your app never imports the package, no hook can help: pass the module with
`--hidden-import` instead, which is unconditional. `hookfix fix` says so and
prints the exact flags when that happens.

## What the demo also shows: the honest boundary

The app has a second reporter, `text_reporter`, that the run above never
exercised. It does not appear in the report, and the frozen binary still fails
if you ask for it:

```console
$ ./dist/demo_proof/demo_proof text
ModuleNotFoundError: No module named 'reporters.text_reporter'
```

That is not a bug — it is the contract. `hookfix` reports what a run actually
imported. Trace the paths you care about (the same ones your smoke tests use),
and the report tells you which call sites are dynamic so you can see what you
might still be missing.
