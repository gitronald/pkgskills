"""Tests for the cross-host ``pkgskills`` script and host discovery."""

from __future__ import annotations

from importlib import metadata

import pytest
from examplehost.cli import HOST as EXAMPLE
from typer.testing import CliRunner

from pkgskills import artifacts as inst
from pkgskills import cli
from pkgskills.testing import Sandbox

runner = CliRunner()


def test_version_flag() -> None:
    result = runner.invoke(cli.pkgskills_app, ["--version"])
    assert result.exit_code == 0
    assert result.output.startswith("pkgskills ")


def test_no_subcommand_prints_help() -> None:
    result = runner.invoke(cli.pkgskills_app, [])
    assert result.exit_code == 0
    assert "hosts" in result.output and "check" in result.output


def test_hosts_with_nothing_registered(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "discover", list)
    result = runner.invoke(cli.pkgskills_app, ["hosts"])
    assert result.exit_code == 0
    assert f"no hosts registered under the {cli.ENTRY_POINT_GROUP}" in result.output


def test_discover_loads_entry_points(monkeypatch: pytest.MonkeyPatch) -> None:
    ep = metadata.EntryPoint(
        "examplehost", "examplehost.cli:HOST", cli.ENTRY_POINT_GROUP
    )
    other = metadata.EntryPoint("cli", "examplehost.cli:app", cli.ENTRY_POINT_GROUP)

    def fake_entry_points(**kwargs: str) -> list[metadata.EntryPoint]:
        return [ep, other] if kwargs.get("group") == cli.ENTRY_POINT_GROUP else []

    monkeypatch.setattr(metadata, "entry_points", fake_entry_points)
    assert cli.discover() == [EXAMPLE]


def test_hosts_lists_registered_hosts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "discover", lambda: [EXAMPLE])
    result = runner.invoke(cli.pkgskills_app, ["hosts"])
    assert "examplehost 1.2.3  (1 skill, 1 rule, 1 agent)" in result.output


def test_check_runs_every_host(box: Sandbox, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "discover", lambda: [EXAMPLE])
    missing = runner.invoke(cli.pkgskills_app, ["check"])
    assert missing.exit_code == 1
    assert "missing" in missing.output
    inst.install(EXAMPLE, box.repo, "local")
    ok = runner.invoke(cli.pkgskills_app, ["check"])
    assert ok.exit_code == 0, ok.output
    assert ok.output.count("ok      local") == 3


def test_check_with_nothing_registered(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "discover", list)
    result = runner.invoke(cli.pkgskills_app, ["check"])
    assert result.exit_code == 1
    assert f"no hosts registered under the {cli.ENTRY_POINT_GROUP}" in result.output
