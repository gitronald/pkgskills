"""Helpers for host test suites.

Everything ``mli`` does is relative to two roots, the home directory and the
repository root, and both are discovered from the environment. Tests that
forget to pin them read and write the developer's real ``~/.claude`` tree.
``sandbox`` pins both in one call, and ``mli_sandbox`` is the same as a pytest
fixture for suites that import it into their ``conftest``.

``wheel_files`` builds a real wheel in-process, because an editable install
resolves package data straight to the checkout and passes whether or not the
build ships it.
"""

from __future__ import annotations

import os
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pytest


@dataclass(frozen=True)
class Sandbox:
    """A pinned home directory and repository root."""

    home: Path
    repo: Path


def sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Sandbox:
    """Pin ``$HOME`` and the working directory to fresh directories under ``tmp_path``.

    The repo gets a ``.git`` marker so root discovery stops there.
    """
    home = tmp_path / "home"
    repo = tmp_path / "repo"
    home.mkdir()
    repo.mkdir()
    (repo / ".git").mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.chdir(repo)
    return Sandbox(home=home, repo=repo)


def wheel_files(project_root: Path, out_dir: Path) -> set[str]:
    """The paths inside a wheel built from ``project_root`` with hatchling."""
    try:
        from hatchling.build import build_wheel
    except ImportError as exc:  # pragma: no cover - dev dependency
        raise RuntimeError("wheel_files needs hatchling installed") from exc
    out_dir.mkdir(parents=True, exist_ok=True)
    cwd = Path.cwd()
    os.chdir(project_root)
    try:
        name = build_wheel(str(out_dir))
    finally:
        os.chdir(cwd)
    with zipfile.ZipFile(out_dir / name) as wheel:
        return set(wheel.namelist())


def __getattr__(name: str) -> object:
    # The fixture is created on first access so importing this module never
    # requires pytest.
    if name == "mli_sandbox":
        import pytest as _pytest

        @_pytest.fixture
        def mli_sandbox(tmp_path: Path, monkeypatch: _pytest.MonkeyPatch) -> Sandbox:
            return sandbox(tmp_path, monkeypatch)

        return mli_sandbox
    raise AttributeError(name)
