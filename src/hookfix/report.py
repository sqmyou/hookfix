"""Render results as a human-readable report."""

from __future__ import annotations

from .model import DiffResult, StaticResult, TraceResult


def _plural(count: int, singular: str, plural: str | None = None) -> str:
    word = singular if count == 1 else (plural or singular + "s")
    return f"{count} {word}"


def format_report(
    *,
    trace: TraceResult,
    static: StaticResult,
    result: DiffResult,
    script: str,
) -> str:
    """Build the multi-section report printed by ``hookfix run``."""
    lines: list[str] = []

    lines.append("hookfix report")
    lines.append("=" * 14)
    lines.append("")
    lines.append(f"script        {script}")
    lines.append(f"python        {trace.python}")
    lines.append(f"exit status   {trace.returncode}")
    lines.append(
        f"scanned       {_plural(len(static.files), 'file')}, "
        f"{_plural(len(static.imports), 'static import')}"
    )
    lines.append(f"observed      {_plural(len(trace.modules), 'module')} imported at runtime")
    lines.append("")

    if not result.missing:
        lines.append("No hidden imports found.")
        lines.append("")
        lines.append(
            "Every third-party module this run imported is also visible to a "
            "static scan, so the build should already include it."
        )
    else:
        lines.append(f"Hidden imports ({len(result.missing)})")
        lines.append("-" * (16 + len(str(len(result.missing)))))
        for name in result.missing:
            lines.append(f"  {name}")
        lines.append("")
        lines.append(
            "These modules were imported at runtime but are invisible to a "
            "static scan. Add them to your build:"
        )
        lines.append("")
        for name in result.missing:
            lines.append(f"  pyinstaller --hidden-import={name} ...")
        lines.append("")
        lines.append("Or generate a hook file for all of them at once:")
        lines.append("")
        lines.append("  hookfix fix")

    if result.stdlib_only:
        lines.append("")
        lines.append(f"Standard library only ({len(result.stdlib_only)})")
        lines.append("-" * (23 + len(str(len(result.stdlib_only)))))
        lines.append("  " + ", ".join(result.stdlib_only))
        lines.append("")
        lines.append(
            "Imported at runtime, but part of the standard library. A freezer "
            "bundles these already; listed for completeness."
        )

    if static.dynamic_sites:
        lines.append("")
        lines.append(f"Dynamic import sites ({len(static.dynamic_sites)})")
        lines.append("-" * (22 + len(str(len(static.dynamic_sites)))))
        for site in static.dynamic_sites[:20]:
            location = f"{site.path}:{site.lineno}:{site.col}"
            target = f" -> {site.target!r}" if site.target else ""
            lines.append(f"  {location}  {site.kind}{target}")
        if len(static.dynamic_sites) > 20:
            lines.append(f"  ... and {len(static.dynamic_sites) - 20} more")
        lines.append("")
        lines.append(
            "These call sites are why the imports above are invisible to "
            "static analysis."
        )

    lines.append("")
    return "\n".join(lines)
