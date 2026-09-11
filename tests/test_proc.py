"""Tests for the repo-pinned subprocess helper."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from pkgskills import proc


def test_pinned_env_strips_only_the_location_variables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in proc.LOCATION_ENV:
        monkeypatch.setenv(name, "/somewhere/else/.git")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", "/dev/null")
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", "/tmp")
    env = proc.pinned_env()
    assert not any(name in env for name in proc.LOCATION_ENV)
    # These change what git *reads*, not which repo it acts on, so they stay.
    assert env["GIT_CONFIG_GLOBAL"] == "/dev/null"
    assert env["GIT_CEILING_DIRECTORIES"] == "/tmp"


def test_run_pins_cwd_and_hides_git_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    monkeypatch.setenv("GIT_DIR", str(tmp_path / "other" / ".git"))
    script = "import os; print(os.getcwd()); print(os.environ.get('GIT_DIR', ''))"
    done = proc.run(root, [sys.executable, "-c", script], capture_output=True)
    cwd, git_dir = done.stdout.splitlines()
    assert Path(cwd).resolve() == root.resolve()
    assert git_dir == ""


def test_run_never_checks_or_shells_out(tmp_path: Path) -> None:
    done = proc.run(tmp_path, [sys.executable, "-c", "raise SystemExit(3)"])
    assert done.returncode == 3
    # A missing binary raises rather than returning a status, so callers can
    # translate it into their own idiom.
    with pytest.raises(FileNotFoundError):
        proc.run(tmp_path, ["pkgskills-no-such-binary-exists"])


def test_run_returns_text_output(tmp_path: Path) -> None:
    done = proc.run(
        tmp_path, [sys.executable, "-c", "print('hi')"], capture_output=True
    )
    assert isinstance(done, subprocess.CompletedProcess)
    assert done.stdout == "hi\n"
