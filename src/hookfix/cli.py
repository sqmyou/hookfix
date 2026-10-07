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
from .model import TraceResult
from .report import format_report
from .scanner import scan
from .spec_writer import render_hook_file, render_spec_patch
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
            "Run a script under a CPython audit hook, record every module it "
            "imports, and compare that against a static scan of the source. "
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
        help="name the generated hook file 'hook-NAME.py'",
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
    """Run ``script`` in a child process under the audit hook and collect the trace."""
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
    static = scan(scan_root, excludes=args.exclude)
    result = diff(trace, static)

    if args.trace_out:
        Path(args.trace_out).write_text(
            json.dumps(trace.to_dict(), indent=2) + "\n", encoding="utf-8"
        )

    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print(format_report(trace=trace, static=static, result=result, script=str(script)))

    # A non-zero exit from the traced program is reported, but the diff itself
    # is still useful, so we only propagate the traced status when there is
    # nothing to report.
    if trace.returncode != 0 and not result.missing:
        return trace.returncode
    return 0


def _cmd_diff(args: argparse.Namespace) -> int:
    trace = _load_trace(args.trace)
    scan_root = args.path or str(Path(args.trace).resolve().parent)
    static = scan(scan_root, excludes=args.exclude)
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
    scan_root = args.path or str(Path(args.trace).resolve().parent)
    static = scan(scan_root, excludes=args.exclude)
    result = diff(trace, static)

    if args.spec:
        rendered = render_spec_patch(result.missing)
    else:
        rendered = render_hook_file(result.missing, module_name=args.module)

    if args.output:
        Path(args.output).write_text(rendered, encoding="utf-8")
        print(f"wrote {args.output} ({len(result.missing)} hidden imports)")
    else:
        print(rendered, end="")
    return 0


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
