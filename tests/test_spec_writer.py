"""Tests for hook/spec rendering."""

from __future__ import annotations

from hookfix.spec_writer import render_hook_file, render_spec_patch


def test_render_hook_file_lists_modules():
    text = render_hook_file(["plugins", "requests"], module_name="app")
    assert "hiddenimports = [" in text
    assert "'plugins'," in text
    assert "'requests'," in text
    assert "hook-app.py" in text


def test_render_hook_file_is_valid_python():
    text = render_hook_file(["plugins"])
    namespace: dict = {}
    exec(compile(text, "<hook>", "exec"), namespace)  # noqa: S102
    assert namespace["hiddenimports"] == ["plugins"]


def test_render_hook_file_handles_empty_list():
    text = render_hook_file([])
    namespace: dict = {}
    exec(compile(text, "<hook>", "exec"), namespace)  # noqa: S102
    assert namespace["hiddenimports"] == []


def test_render_spec_patch_is_valid_python():
    text = render_spec_patch(["numpy"])
    namespace: dict = {}
    exec(compile(text, "<spec>", "exec"), namespace)  # noqa: S102
    assert namespace["hiddenimports"] == ["numpy"]
