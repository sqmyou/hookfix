"""Render results as a human-readable report."""

from __future__ import annotations

from .model import DiffResult, StaticResult, TraceResult


def _plural(count: int, singular: str, plural: str | None = None) -> str:
    word = singular if count == 1 else (plural or singular + "s")
    return f"{count} {word}"


def _grouped(names: list[str]) -> list[str]:
    """Group names by top-level package, e.g. ``yaml.*`` for 17 yaml modules.

    A hidden third-party package arrives as a long list of submodules, which
    buries the packages that only contributed one or two. Showing the package
    once, with its children indented, keeps the shape of the list readable.
    """
    groups: dict[str, list[str]] = {}
    for name in names:
        groups.setdefault(name.split(".")[0], []).append(name)
    lines: list[str] = []
    for top in sorted(groups):
        children = groups[top]
        if len(children) == 1:
            lines.append(f"  {children[0]}")
        else:
            lines.append(f"  {top}.*  ({len(children)} modules)")
            for child in children:
                lines.append(f"      {child}")
    return lines


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
        lines.extend(_grouped(result.missing))
        lines.append("")
        lines.append(
            "These modules were imported at runtime but are invisible to a "
            "static scan. Add them to your build:"
        )
        lines.append("")
        # A module with children is redundant in the flag list: --hidden-import
        # on the parent pulls the whole package in, so list only the leaves.
        tops = {name.split(".")[0] for name in result.missing}
        leaves = [
            name
            for name in result.missing
            if not any(other != name and other.startswith(name + ".") for other in result.missing)
        ]
        flags = "".join(f" --hidden-import={name}" for name in leaves)
        if len(flags) <= 100:
            lines.append(f"  pyinstaller{flags} ...")
        else:
            lines.append("  pyinstaller ...")
            for name in leaves:
                lines.append(f"      --hidden-import={name}")
        if tops - {name.split(".")[0] for name in leaves}:
            lines.append("")
            lines.append(
                "A package listed above is covered by its own modules; the "
                "freezer pulls the package in with them."
            )
        lines.append("")
        lines.append("Or generate a hook file for all of them at once:")
        lines.append("")
        lines.append("  hookfix fix")

    if result.unresolved:
        lines.append("")
        lines.append(f"Unresolved imports ({len(result.unresolved)})")
        lines.append("-" * (22 + len(str(len(result.unresolved)))))
        for name in result.unresolved:
            lines.append(f"  {name}")
        lines.append("")
        lines.append(
            "The program tried to import these but nothing could resolve them, "
            "so there is no file to bundle. Either they are missing from this "
            "environment (install them), or they are built in and always "
            "available. Not a build setting."
        )

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
