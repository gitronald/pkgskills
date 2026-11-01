"""Shared fixtures: a pinned sandbox and the two example hosts."""

from __future__ import annotations

from pathlib import Path

import pytest

from pkgskills.testing import Sandbox, sandbox


@pytest.fixture
def box(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Sandbox:
    """A fresh ``$HOME`` and repo root, with the cwd inside the repo."""
    return sandbox(tmp_path, monkeypatch)


@pytest.fixture
def no_outer_markers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Root discovery must not depend on what sits above the temporary directory.

    A walk that passes the sandbox's home goes on to the real parents, where a
    machine can hold a stray ``.git``, ``.claude``, or ``.codex``.
    """
    exists = Path.exists
    is_dir = Path.is_dir
    outside = {
        parent / marker
        for parent in tmp_path.parents
        for marker in (".git", ".claude", ".codex")
    }
    monkeypatch.setattr(
        Path, "exists", lambda path: path not in outside and exists(path)
    )
    monkeypatch.setattr(
        Path, "is_dir", lambda path: path not in outside and is_dir(path)
    )
