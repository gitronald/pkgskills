"""Tests for the helpers host suites import."""

from __future__ import annotations

import os
from pathlib import Path

from mli.testing import Sandbox, wheel_files

PROJECT = Path(__file__).parents[1]


def test_sandbox_pins_home_and_cwd(box: Sandbox) -> None:
    assert Path.home() == box.home
    assert Path.cwd() == box.repo
    assert (box.repo / ".git").is_dir()
    assert os.environ["HOME"] == str(box.home)


def test_wheel_ships_the_package(tmp_path: Path) -> None:
    files = wheel_files(PROJECT, tmp_path / "dist")
    assert "mli/rendering.py" in files
    assert "mli/py.typed" in files
    assert not any(name.startswith("tests/") for name in files)
