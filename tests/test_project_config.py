"""Facts the project's own configuration states in more than one place."""

from __future__ import annotations

import tomllib
from pathlib import Path

import yaml

ROOT = Path(__file__).parents[1]


def _version(text: str) -> tuple[int, ...]:
    return tuple(int(part) for part in text.split("."))


def test_the_python_floor_agrees_everywhere() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    floor = project["project"]["requires-python"].removeprefix(">=")
    assert project["tool"]["ruff"]["target-version"] == "py" + floor.replace(".", "")
    assert project["tool"]["pyrefly"]["python-version"] == floor

    workflow = (ROOT / ".github" / "workflows" / "test.yml").read_text(encoding="utf-8")
    matrix = yaml.safe_load(workflow)["jobs"]["test"]["strategy"]["matrix"]
    assert min(matrix["python-version"], key=_version) == floor
