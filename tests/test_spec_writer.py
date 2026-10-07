"""Tests for hook/spec rendering."""

from __future__ import annotations

from hookfix.spec_writer import (
    hook_targets,
    render_hook_file,
    render_nuitka_options,
    render_spec_patch,
)


def test_hook_targets_uses_top_level_package():
    # A hook must be keyed to a module PyInstaller processes. The hidden imports
    # are submodules, so the key is their top-level package.
    assert hook_targets(["reporters.json_reporter"]) == ["reporters"]
    assert hook_targets(["plugins.report", "plugins.load"]) == ["plugins"]
    assert hook_targets(["yaml"]) == ["yaml"]
    assert hook_targets([]) == []


def test_render_hook_file_lists_modules():
    text = render_hook_file(["plugins.report"], module_name="plugins")
    assert "hiddenimports = [" in text
    assert "'plugins.report'," in text
    assert "hook-plugins.py" in text


def test_render_hook_file_is_valid_python():
    text = render_hook_file(["plugins"], module_name="plugins")
    namespace: dict = {}
    exec(compile(text, "<hook>", "exec"), namespace)  # noqa: S102
    assert namespace["hiddenimports"] == ["plugins"]


def test_render_hook_file_handles_empty_list():
    text = render_hook_file([], module_name="plugins")
    namespace: dict = {}
    exec(compile(text, "<hook>", "exec"), namespace)  # noqa: S102
    assert namespace["hiddenimports"] == []


def test_render_spec_patch_is_valid_python():
    text = render_spec_patch(["numpy"])
    namespace: dict = {}
    exec(compile(text, "<spec>", "exec"), namespace)  # noqa: S102
    assert namespace["hiddenimports"] == ["numpy"]


def test_render_nuitka_options_lists_one_flag_per_module():
    text = render_nuitka_options(["plugins.report", "yaml"])
    assert "--include-module=plugins.report" in text
    assert "--include-module=yaml" in text
    # No PyInstaller hook syntax leaks into the Nuitka form.
    assert "hiddenimports" not in text


def test_render_nuitka_options_handles_empty_list():
    text = render_nuitka_options([])
    assert "--include-module=" not in text
    assert "(no hidden imports)" in text
