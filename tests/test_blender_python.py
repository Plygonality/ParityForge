"""Blender's bundled interpreter is not the system Python."""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from parityforge.hosts.blender_python import find_blender_python
from parityforge.hosts.runtime import ensure_importable, missing_modules


def _touch_exec(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\n", encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


def test_finds_linux_tarball_python(tmp_path: Path) -> None:
    blender = tmp_path / "blender"
    blender.write_text("", encoding="utf-8")
    blender.chmod(blender.stat().st_mode | stat.S_IEXEC)
    generic = tmp_path / "4.5" / "python" / "bin" / "python3"
    specific = tmp_path / "4.5" / "python" / "bin" / "python3.11"
    _touch_exec(generic)
    _touch_exec(specific)
    assert find_blender_python(blender) == specific


def test_finds_macos_resources_python(tmp_path: Path) -> None:
    blender = tmp_path / "Blender.app" / "Contents" / "MacOS" / "Blender"
    _touch_exec(blender)
    python = tmp_path / "Blender.app" / "Contents" / "Resources" / "4.5" / "python" / "bin" / "python3.11"
    _touch_exec(python)
    assert find_blender_python(blender) == python


def test_missing_blender_python_is_none(tmp_path: Path) -> None:
    blender = tmp_path / "blender"
    _touch_exec(blender)
    assert find_blender_python(blender) is None
    assert find_blender_python(tmp_path / "absent") is None


def test_missing_module_message_exits() -> None:
    assert missing_modules(("json",)) == []
    with pytest.raises(SystemExit) as caught:
        ensure_importable(("this_module_is_not_installed_parityforge",), hint="install it into this interpreter")
    assert caught.value.code == 1


def test_installed_blender_python_is_the_real_layout() -> None:
    env = os.environ.get("PARITYFORGE_BLENDER")
    if not env or not Path(env).is_file():
        pytest.skip("PARITYFORGE_BLENDER is unset")
    python = find_blender_python(Path(env))
    assert python is not None
    assert python.is_file()
