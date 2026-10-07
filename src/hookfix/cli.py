"""Command line interface.

Three subcommands, each a step of the same workflow:

``hookfix run``   run a script under the tracer and print a report
``hookfix diff``  compare a saved trace against a static scan
``hookfix fix``   turn a saved trace into a hook file or spec snippet

``run`` is the whole workflow in one command; ``diff`` and ``fix`` exist so the
trace can be taken once (for example in CI, on the platform that will actually
be packaged) and inspected later.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path

from . import __version__
from .differ import diff
from .errors import HookfixError
from .model import StaticResult, TraceResult
from .report import format_report
from .scanner import scan
from .spec_writer import hook_targets, render_hook_file, render_spec_patch
from .tracer import parse_audit_log


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hookfix",
        description="Find the hidden imports that break your frozen Python app.",
    )
    parser.add_argument("--version", action="version", version=f"hookfix {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run = subparsers.add_parser(
        "run",
        help="run a script under the tracer and report hidden imports",
        description=(
            "Run a script under a meta path import tracer, record every module "
            "it imports, and compare that against a static scan of the source. "
            "Arguments after '--' are passed through to the traced script."
        ),
    )
    run.add_argument("script", help="path to the entry point to trace")
    run.add_argument(
        "--path",
        default=None,
        help="directory to scan statically (default: the script's directory)",
    )
    run.add_argument(
        "--exclude",
        action="append",
        default=[],
        metavar="DIR",
        help="additional directory name to skip while scanning (repeatable)",
    )
    run.add_argument(
        "--trace-out",
        default=None,
        metavar="FILE",
        help="write the raw runtime trace to FILE as JSON",
    )
    run.add_argument(
        "--json",
        action="store_true",
        help="print the diff as JSON instead of a human-readable report",
    )
    run.add_argument(
        "--quiet",
        action="store_true",
        help="suppress the traced program's own output",
    )

    diff_cmd = subparsers.add_parser(
        "diff",
        help="compare a saved trace against a static scan",
        description="Read a trace written by 'hookfix run --trace-out' and diff it.",
    )
    diff_cmd.add_argument("trace", help="path to a trace JSON file")
    diff_cmd.add_argument(
        "--path",
        default=None,
        metavar="DIR",
        help="directory to scan statically (default: the trace's directory)",
    )
    diff_cmd.add_argument(
        "--exclude",
        action="append",
        default=[],
        metavar="DIR",
        help="additional directory name to skip while scanning (repeatable)",
    )
    diff_cmd.add_argument("--json", action="store_true", help="print the diff as JSON")

    fix = subparsers.add_parser(
        "fix",
        help="generate a hook file or spec snippet from a trace",
        description="Turn a saved trace into build configuration.",
    )
    fix.add_argument("trace", help="path to a trace JSON file")
    fix.add_argument(
        "--path",
        default=None,
        metavar="DIR",
        help="directory to scan statically (default: the trace's directory)",
    )
    fix.add_argument(
        "--exclude",
        action="append",
        default=[],
        metavar="DIR",
        help="additional directory name to skip while scanning (repeatable)",
    )
    fix.add_argument(
        "--module",
        default=None,
        metavar="NAME",
        help=(
            "name the generated hook file 'hook-NAME.py'. NAME must be a module "
            "PyInstaller processes; naming it after the entry script produces a "
            "hook that is never read (default: the top-level package of each "
            "hidden import)"
        ),
    )
    fix.add_argument(
        "--spec",
        action="store_true",
        help="emit a spec-file snippet instead of a hook file",
    )
    fix.add_argument(
        "-o",
        "--output",
        default=None,
        metavar="FILE",
        help="write to FILE instead of stdout",
    )

    return parser


def _trace_script(script: Path, script_args: Sequence[str], quiet: bool) -> TraceResult:
    """Run ``script`` in a child process under the tracer and collect the trace."""
    with tempfile.TemporaryDirectory(prefix="hookfix-") as tmp:
        logfile = Path(tmp) / "imports.log"
        cmd: list[str] = [
            sys.executable,
            "-m",
            "hookfix._bootstrap",
            str(logfile),
            str(script),
            *script_args,
        ]
        completed = subprocess.run(
            cmd,
            stdout=subprocess.DEVNULL if quiet else None,
            stderr=subprocess.DEVNULL if quiet else None,
            check=False,
        )
        log_text = logfile.read_text(encoding="utf-8") if logfile.exists() else ""

    modules, origins = parse_audit_log(log_text)
    return TraceResult(
        modules=sorted(modules),
        origins=origins,
        returncode=completed.returncode,
        entry=str(script),
    )


def _load_trace(path: str) -> TraceResult:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return TraceResult.from_dict(data)


def _cmd_run(args: argparse.Namespace) -> int:
    script = Path(args.script).resolve()
    if not script.exists():
        raise HookfixError(f"script does not exist: {script}")

    trace = _trace_script(script, args.script_args, args.quiet)

    scan_root = Path(args.path).resolve() if args.path else script.parent
    static = scan(scan_root, excludes=args.exclude, entry=script)
    result = diff(trace, static)

    if args.trace_out:
        Path(args.trace_out).write_text(
            json.dumps(trace.to_dict(), indent=2) + "\n", encoding="utf-8"
        )

    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print(format_report(trace=trace, static=static, result=result, script=str(script)))

    # A trace of a program that crashed is incomplete by construction: the code
    # that never ran is invisible, so any advice drawn from it is partial. Say
    # so on stderr and exit non-zero rather than report a clean bill of health.
    if trace.returncode != 0:
        print(
            f"warning: the traced program exited with status {trace.returncode}; "
            "the report reflects only the part that ran and is likely incomplete",
            file=sys.stderr,
        )
        return trace.returncode
    return 0


def _scan_for_trace(trace: TraceResult, args: argparse.Namespace) -> StaticResult:
    """Re-scan for a saved trace, using the entry point recorded in it.

    A schema-1 trace has no entry point, and without one there is no way to
    know which modules the freezer can reach. Guessing would produce a
    confidently wrong answer, so say so instead.
    """
    if not trace.entry:
        raise HookfixError(
            f"{args.trace} has no entry point recorded (it predates schema 2); "
            "re-run 'hookfix run --trace-out' to regenerate it"
        )
    scan_root = args.path or str(Path(trace.entry).resolve().parent)
    return scan(scan_root, excludes=args.exclude, entry=trace.entry)


def _cmd_diff(args: argparse.Namespace) -> int:
    trace = _load_trace(args.trace)
    static = _scan_for_trace(trace, args)
    result = diff(trace, static)

    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print(
            format_report(
                trace=trace,
                static=static,
                result=result,
                script="(from trace)",
            )
        )
    return 0


def _cmd_fix(args: argparse.Namespace) -> int:
    trace = _load_trace(args.trace)
    static = _scan_for_trace(trace, args)
    result = diff(trace, static)

    if args.spec:
        rendered = render_spec_patch(result.missing)
        if args.output:
            Path(args.output).write_text(rendered, encoding="utf-8")
            print(f"wrote {args.output} ({len(result.missing)} hidden imports)")
        else:
            print(rendered, end="")
        return 0

    # A hook only fires for a module PyInstaller processes. A module that is
    # hidden *because nothing imports it* is by definition not processed, so no
    # hook can cover it -- a hook file for it would be dead. Those modules go to
    # ``--hidden-import`` instead, which is unconditional.
    reachable = set(static.reachable)
    hookable = [name for name in result.missing if name.split(".")[0] in reachable]
    unconditional = [name for name in result.missing if name.split(".")[0] not in reachable]

    if args.module is not None:
        # Explicit request. Honour it faithfully: ``--module reporters`` means
        # every hidden import that belongs to ``reporters``. But refuse a hook
        # that cannot fire -- naming it after the entry script is the classic
        # mistake. ``_scan_for_trace`` already rejected a trace with no entry.
        entry_name = Path(trace.entry or "").stem
        if Path(args.module).stem == entry_name:
            raise HookfixError(
                f"a hook named after the entry script ({args.module}) is never "
                "read: PyInstaller knows the entry script as __main__. Name the "
                "hook after a module your program imports, or drop --module to "
                "let hookfix choose."
            )
        top = args.module.split(".")[0]
        for_this = [name for name in result.missing if name.split(".")[0] == top]
        if not for_this:
            for_this = list(result.missing)
        targets = {args.module: for_this}
    else:
        targets = {
            target: [name for name in hookable if name.split(".")[0] == target]
            for target in hook_targets(hookable)
        }

    if not targets:
        print(
            "no hook file written: none of the hidden imports are modules "
            "PyInstaller processes, so a hook would never fire."
        )
        _print_hidden_import_advice(unconditional)
        return 0

    if args.output and Path(args.output).is_dir():
        for target, names in targets.items():
            path = Path(args.output) / f"hook-{target}.py"
            path.write_text(render_hook_file(names, module_name=target), encoding="utf-8")
            print(f"wrote {path} ({len(names)} hidden imports)")
    elif args.output:
        target, names = next(iter(targets.items()))
        Path(args.output).write_text(
            render_hook_file(names, module_name=target), encoding="utf-8"
        )
        print(f"wrote {args.output} ({len(names)} hidden imports)")
    elif len(targets) == 1:
        target, names = next(iter(targets.items()))
        print(render_hook_file(names, module_name=target), end="")
    else:
        # Several packages; a hook file is one file, so print them separated.
        for i, (target, names) in enumerate(targets.items()):
            if i:
                print()
            print(render_hook_file(names, module_name=target), end="")

    if unconditional:
        _print_hidden_import_advice(unconditional)
    return 0


def _print_hidden_import_advice(modules: Sequence[str]) -> None:
    if not modules:
        return
    flags = " ".join(f"--hidden-import={name}" for name in modules)
    print(
        f"\n{len(modules)} module(s) cannot be covered by a hook (nothing imports "
        f"them, so PyInstaller never processes them). Pass these instead:\n\n"
        f"  pyinstaller {flags} ...\n"
    )


def main(argv: Sequence[str] | None = None) -> int:
    raw = list(sys.argv[1:] if argv is None else argv)
    # Split pass-through arguments before argparse sees them, so the traced
    # script's own flags are not mistaken for hookfix's.
    script_args: list[str] = []
    if "--" in raw:
        split = raw.index("--")
        script_args = raw[split + 1 :]
        raw = raw[:split]

    parser = _build_parser()
    args = parser.parse_args(raw)
    args.script_args = script_args

    handlers = {"run": _cmd_run, "diff": _cmd_diff, "fix": _cmd_fix}
    try:
        return handlers[args.command](args)
    except HookfixError as exc:
        print(f"hookfix: error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
