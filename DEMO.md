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
ModuleNotFoundError: No module named 'reporters'
[PYI-2105:ERROR] Failed to execute script 'main' due to unhandled exception!
```

The classic symptom, and the reason this tool exists.

## 3. hookfix finds the hidden import

```console
$ hookfix run main.py --path . --quiet --trace-out trace.json

hookfix report
==============

script        /tmp/hookfix_demo/main.py
python        3.13.15
exit status   0
scanned       4 files, 4 static imports
observed      18 modules imported at runtime

Hidden imports (1)
-----------------
  reporters.json_reporter

These modules were imported at runtime but are invisible to a static scan.
Add them to your build:

  pyinstaller --hidden-import=reporters.json_reporter ...

Dynamic import sites (1)
------------------------
  main.py:25:12  importlib.import_module

These call sites are why the imports above are invisible to static analysis.
```

## 4. Generate the build configuration

```console
$ hookfix fix trace.json --path . --spec
hiddenimports = [
    'reporters.json_reporter',
]
```

or a ready-to-use hook file:

```console
$ hookfix fix trace.json --path . --module main -o hook-main.py
wrote hook-main.py (1 hidden imports)
```

## 5. The frozen binary works

```console
$ pyinstaller --onedir --name demo_proof --paths . \
      --hidden-import=reporters.json_reporter main.py
$ ./dist/demo_proof/demo_proof json
{
  "status": "ok",
  "items": 3
}
```

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
