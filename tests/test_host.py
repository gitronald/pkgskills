"""Tests for the host declaration and its derived command strings."""

from __future__ import annotations

import pytest
from examplehost.cli import HOST as EXAMPLE
from solohost.cli import HOST as SOLO

from mli.harness import CLAUDE_CODE, Harness, Kind
from mli.host import Agent, Host, Rule, Skill


def test_invocation_and_commands_per_mode() -> None:
    assert EXAMPLE.invocation("global") == "examplehost"
    assert EXAMPLE.invocation("local") == "uv run examplehost"
    assert EXAMPLE.install_command("global") == "examplehost install"
    assert (
        EXAMPLE.install_command("local", force=True)
        == "uv run examplehost install --local --force"
    )
    assert (
        EXAMPLE.check_command("local") == "uv run examplehost install --local --check"
    )
    assert EXAMPLE.skill_command("global", "add") == "examplehost skill add"
    assert SOLO.skill_command("local") == "uv run solohost skill"


def test_skill_shape() -> None:
    skill = EXAMPLE.skills[0]
    assert skill.dispatches and skill.subcommands == ("add", "close")
    assert skill.source_for("close") == "skills/close.md"
    with pytest.raises(KeyError):
        skill.source_for("nope")
    assert not SOLO.skills[0].dispatches


def test_lookup_by_kind_and_name() -> None:
    assert EXAMPLE.artifact(Kind.RULE, "examplehost") == EXAMPLE.rules[0]
    assert EXAMPLE.of_kind(Kind.AGENT) == EXAMPLE.agents
    with pytest.raises(KeyError):
        EXAMPLE.artifact(Kind.SKILL, "nope")
    assert set(EXAMPLE.skill_sources()) == {"add", "close"}


def test_version_falls_back_when_no_distribution_is_installed() -> None:
    host = Host(dist="no-such-dist-xyz", cli="x", prompts="solohost.prompts")
    assert host.resolved_version() == "0.0.0"


def test_validation_rejects_bad_declarations() -> None:
    with pytest.raises(ValueError, match="needs a dist"):
        Host(dist="", cli="x", prompts="p")
    with pytest.raises(ValueError, match="declares no sources"):
        Host(dist="d", cli="c", prompts="p", artifacts=(Skill("s", ()),))
    with pytest.raises(ValueError, match="duplicate stems"):
        Host(
            dist="d",
            cli="c",
            prompts="p",
            artifacts=(Skill("s", ("a/x.md", "b/x.md")),),
        )
    with pytest.raises(ValueError, match="duplicate rule"):
        Host(
            dist="d",
            cli="c",
            prompts="p",
            artifacts=(Rule("r", "r.md"), Rule("r", "s.md")),
        )
    bare = Harness(name="bare", config_dir=".bare", layout={Kind.SKILL: "{name}.md"})
    with pytest.raises(ValueError, match="cannot install agent"):
        Host(
            dist="d",
            cli="c",
            prompts="p",
            harness=bare,
            artifacts=(Agent("a", "a.md"),),
        )


def test_ambiguous_skill_bodies_are_rejected_on_lookup() -> None:
    host = Host(
        dist="d",
        cli="c",
        prompts="p",
        artifacts=(Skill("one", ("x/add.md",)), Skill("two", ("y/add.md",))),
    )
    with pytest.raises(ValueError, match="more than one skill"):
        host.skill_sources()


def test_claude_code_layout() -> None:
    assert (
        CLAUDE_CODE.relative_path(Kind.SKILL, "x").as_posix()
        == ".claude/skills/x/SKILL.md"
    )
    assert CLAUDE_CODE.relative_path(Kind.RULE, "x").as_posix() == ".claude/rules/x.md"
    assert (
        CLAUDE_CODE.relative_path(Kind.AGENT, "x").as_posix() == ".claude/agents/x.md"
    )
    with pytest.raises(ValueError):
        Harness(name="h", config_dir=".h").relative_path(Kind.SKILL, "x")
