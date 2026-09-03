"""Shared fixtures: a pinned sandbox and the two example hosts."""

from __future__ import annotations

from pathlib import Path

import pytest

from mli.testing import Sandbox, sandbox


@pytest.fixture
def box(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Sandbox:
    """A fresh ``$HOME`` and repo root, with the cwd inside the repo."""
    return sandbox(tmp_path, monkeypatch)
