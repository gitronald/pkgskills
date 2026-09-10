"""Tests for the host declaration and its derived command strings."""

from __future__ import annotations

import pytest
from examplehost.cli import HOST as EXAMPLE
from multihost.cli import HOST as MULTI
from solohost.cli import HOST as SOLO

from mli.harness import CLAUDE_CODE, Harness, Kind
from mli.host import Agent, Doc, Host, Rule, Skill


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
    assert SOLO.skill_command("local", "use-solo") == "uv run solohost skill use-solo"


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


def test_skill_bodies_are_keyed_by_stem_only_when_dispatching() -> None:
    # A dispatcher's bodies answer to their stems, which are its subcommands.
    assert EXAMPLE.skills[0].body_names == ("add", "close")
    # A single-source skill answers to the skill's name, whatever the file is
    # called: `skill.md` is not what the model knows `use-solo` as.
    assert SOLO.skills[0].body_names == ("use-solo",)
    assert set(SOLO.skill_sources()) == {"use-solo"}
    assert set(MULTI.skill_sources()) == {"tidy", "audit"}
    assert MULTI.skill_sources()["audit"][1] == "skills/audit-body.md"


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


def test_modes_default_to_both_and_a_host_can_restrict_them() -> None:
    assert EXAMPLE.modes == ("global", "local")
    assert EXAMPLE.default_mode == "global"
    assert EXAMPLE.supports_mode("local") and EXAMPLE.supports_mode("global")
    # A host bound to one repository has no use for global mode.
    assert MULTI.modes == ("local",)
    assert MULTI.default_mode == "local"
    assert not MULTI.supports_mode("global")


def test_validation_rejects_bad_modes() -> None:
    with pytest.raises(ValueError, match="at least one install mode"):
        Host(dist="d", cli="c", prompts="p", modes=())
    with pytest.raises(ValueError, match="unknown install mode"):
        Host(dist="d", cli="c", prompts="p", modes=("repo",))  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="install mode twice"):
        Host(dist="d", cli="c", prompts="p", modes=("local", "local"))


def test_ambiguous_skill_bodies_are_rejected_at_construction() -> None:
    # Two dispatchers whose stems overlap.
    with pytest.raises(ValueError, match="more than one skill"):
        Host(
            dist="d",
            cli="c",
            prompts="p",
            artifacts=(
                Skill("one", ("x/add.md", "x/close.md")),
                Skill("two", ("y/add.md", "y/drop.md")),
            ),
        )
    # A dispatcher stem that collides with a single-source skill's own name:
    # the two namespaces share one `skill <name>` argument, so this is
    # ambiguous even though neither declaration repeats itself.
    with pytest.raises(ValueError, match="more than one skill"):
        Host(
            dist="d",
            cli="c",
            prompts="p",
            artifacts=(
                Skill("one", ("x/audit.md", "x/close.md")),
                Skill("audit", ("y/audit-body.md",)),
            ),
        )


def test_docs_are_declared_apart_from_artifacts() -> None:
    # A doc is never installed, so it must not reach anything that walks
    # `artifacts` — the install, the check, or the harness's layout.
    assert [d.name for d in MULTI.docs] == ["tidy/fields", "audit/severity"]
    assert all(not isinstance(art, Doc) for art in MULTI.artifacts)
    assert MULTI.doc("tidy/fields").source == "references/tidy/fields.md"
    with pytest.raises(KeyError):
        MULTI.doc("nope")
    assert MULTI.doc_command("local", "tidy/fields") == (
        "uv run multihost doc tidy/fields"
    )
    assert MULTI.doc_command("local") == "uv run multihost doc"


def test_validation_rejects_bad_docs() -> None:
    with pytest.raises(ValueError, match="duplicate doc"):
        Host(
            dist="d",
            cli="c",
            prompts="multihost.prompts",
            docs=(
                Doc("x", "references/tidy/fields.md"),
                Doc("x", "references/audit/severity.md"),
            ),
        )
    # Nothing else ever reads a doc's source, so a typo would surface only when
    # a model ran the command; it is caught at construction instead.
    with pytest.raises(ValueError, match="no such prompt"):
        Host(
            dist="d",
            cli="c",
            prompts="multihost.prompts",
            docs=(Doc("x", "references/nope.md"),),
        )


def test_render_cli_defaults_to_the_hosts_setting() -> None:
    # multihost declares it once; every body and doc it ships inherits.
    assert MULTI.render_cli
    assert all(art.render_cli is None for art in MULTI.artifacts)
    assert all(MULTI.renders_cli(art) for art in MULTI.artifacts)
    assert all(MULTI.renders_cli(doc) for doc in MULTI.docs)
    # examplehost leaves the host default off and opts in per declaration.
    assert not EXAMPLE.render_cli
    assert EXAMPLE.renders_cli(EXAMPLE.rules[0])
    assert not EXAMPLE.renders_cli(EXAMPLE.agents[0])
    # An explicit `False` outranks a host that says `True`, so a host-wide
    # default never forces the token on a body that means it literally.
    opted_out = Host(
        dist="d",
        cli="c",
        prompts="multihost.prompts",
        render_cli=True,
        docs=(Doc("x", "references/tidy/fields.md", render_cli=False),),
    )
    assert not opted_out.renders_cli(opted_out.docs[0])


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


def test_claude_code_loading_discipline_per_kind() -> None:
    # A global skill wins by name; rules and agents are auto-loaded from both.
    assert CLAUDE_CODE.shadows(Kind.SKILL)
    assert not CLAUDE_CODE.both_load(Kind.SKILL)
    for kind in (Kind.RULE, Kind.AGENT):
        assert CLAUDE_CODE.both_load(kind)
        assert not CLAUDE_CODE.shadows(kind)
    # A harness that says nothing loads every kind from both bases.
    bare = Harness(name="bare", config_dir=".bare")
    assert all(bare.both_load(kind) for kind in Kind)
