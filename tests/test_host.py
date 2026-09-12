"""Tests for the host declaration and its derived command strings."""

from __future__ import annotations

import pytest
from examplehost.cli import HOST as EXAMPLE
from multihost.cli import HOST as MULTI
from solohost.cli import HOST as SOLO

from pkgskills.frontmatter import split_frontmatter
from pkgskills.harness import CLAUDE_CODE, Harness, Kind
from pkgskills.host import Agent, Doc, Host, Rule, Skill, source_name
from pkgskills.spec import SPEC, SpecError


def test_source_name_reads_the_directory_of_a_conformant_skill() -> None:
    # The spec's layout: `<name>/SKILL.md`, so the directory names the source.
    assert source_name("use-solo/SKILL.md") == "use-solo"
    assert source_name("skills/nested/pdf-processing/SKILL.md") == "pdf-processing"
    # A flat source keeps naming itself by its stem.
    assert source_name("skills/audit-body.md") == "audit-body"
    assert source_name("skill.md") == "skill"
    # The match is exact, as the spec writes it; anything else is a flat file
    # that happens to be called something similar.
    assert source_name("skills/x/skill.md") == "skill"
    assert source_name("skills/x/Skill.MD") == "Skill"
    # No parent to read, so there is nothing but the stem to go on.
    assert source_name("SKILL.md") == "SKILL"


def test_skill_names_are_checked_against_the_spec_grammar() -> None:
    assert SPEC.valid_name("pdf-processing")
    assert SPEC.valid_name("a1")
    assert not SPEC.valid_name("")
    assert not SPEC.valid_name("PDF-Processing")
    assert not SPEC.valid_name("-pdf")
    assert not SPEC.valid_name("pdf-")
    assert not SPEC.valid_name("pdf--processing")
    assert not SPEC.valid_name("pdf processing")
    assert not SPEC.valid_name("edit/refs")
    assert not SPEC.valid_name("a" * 65)


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
    assert skill.source_for("close") == "skills/close/SKILL.md"
    with pytest.raises(KeyError):
        skill.source_for("nope")
    assert not SOLO.skills[0].dispatches


def test_lookup_by_kind_and_name() -> None:
    assert EXAMPLE.artifact(Kind.RULE, "examplehost") == EXAMPLE.rules[0]
    assert EXAMPLE.of_kind(Kind.AGENT) == EXAMPLE.agents
    with pytest.raises(KeyError):
        EXAMPLE.artifact(Kind.SKILL, "nope")
    assert set(EXAMPLE.skill_sources()) == {"add", "close"}


def test_skill_bodies_are_keyed_by_source_name_only_when_dispatching() -> None:
    # A dispatcher's bodies answer to their source names, which are its
    # subcommands.
    assert EXAMPLE.skills[0].body_names == ("add", "close")
    assert SOLO.skills[0].body_names == ("use-solo",)
    assert set(SOLO.skill_sources()) == {"use-solo"}
    assert set(MULTI.skill_sources()) == {"tidy", "audit"}
    # A single-source skill answers to the skill's name whatever its source is
    # called, so a host that has not moved to `<name>/SKILL.md` keeps working.
    # Every fixture is conformant now, so the unmigrated shape is declared here
    # rather than shipped on disk.
    flat = Host(
        dist="d",
        cli="c",
        prompts="p",
        artifacts=(
            Skill("audit", ("skills/audit-body.md",)),
            Skill("two", ("x/add.md", "x/drop.md")),
        ),
    )
    assert flat.skills[0].body_names == ("audit",)
    assert flat.skill_sources()["audit"][1] == "skills/audit-body.md"
    # A flat dispatcher still takes its subcommands from the stems.
    assert flat.skills[1].body_names == ("add", "drop")


def test_version_falls_back_when_no_distribution_is_installed() -> None:
    host = Host(dist="no-such-dist-xyz", cli="x", prompts="solohost.prompts")
    assert host.resolved_version() == "0.0.0"


def test_validation_rejects_bad_declarations() -> None:
    with pytest.raises(ValueError, match="needs a dist"):
        Host(dist="", cli="x", prompts="p")
    with pytest.raises(ValueError, match="declares no sources"):
        Host(dist="d", cli="c", prompts="p", artifacts=(Skill("s", ()),))
    with pytest.raises(SpecError, match="contains uppercase characters"):
        Host(dist="d", cli="c", prompts="p", artifacts=(Skill("Bad Name", ("x.md",)),))
    with pytest.raises(ValueError, match="duplicate names"):
        Host(
            dist="d",
            cli="c",
            prompts="p",
            artifacts=(Skill("s", ("a/x.md", "b/x.md")),),
        )
    # Same collision under the conformant layout: the directory names it, so
    # two `SKILL.md` files only collide when their directories do.
    with pytest.raises(ValueError, match="duplicate names"):
        Host(
            dist="d",
            cli="c",
            prompts="p",
            artifacts=(Skill("s", ("a/x/SKILL.md", "b/x/SKILL.md")),),
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
    assert MULTI.doc("tidy/fields").source == "tidy/references/fields.md"
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
                Doc("x", "tidy/references/fields.md"),
                Doc("x", "audit/references/severity.md"),
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
        docs=(Doc("x", "tidy/references/fields.md", render_cli=False),),
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


@pytest.mark.parametrize("host", [EXAMPLE, SOLO, MULTI], ids=lambda h: h.dist)
def test_conformant_sources_match_the_spec_layout(host: Host) -> None:
    """Every skill source is `<name>/SKILL.md` with matching frontmatter.

    The spec ties a skill's frontmatter `name` to its parent directory, and
    `pkgskills` derives the source's name from that directory — so a source that
    drifted apart would key a body under one name while a skills linter read
    another. `pkgskills` still accepts a flat source, but no fixture ships one: the
    tree these hosts bundle is what a host author copies, and it has to pass a
    linter as it stands.
    """
    for skill in host.skills:
        for source in skill.sources:
            assert source.endswith("/" + SPEC.entry_file), (
                f"{source} is not a spec-conformant skill directory"
            )
            front, _ = split_frontmatter(host.read(source))
            assert front is not None, f"{source} has no frontmatter"
            declared = front.get("name")
            assert declared == source_name(source), (
                f"{source}: frontmatter names {declared!r}, "
                f"directory names {source_name(source)!r}"
            )
            assert SPEC.valid_name(str(declared))


@pytest.mark.parametrize("host", [EXAMPLE, SOLO, MULTI], ids=lambda h: h.dist)
def test_a_skills_references_live_inside_its_own_directory(host: Host) -> None:
    """A doc namespaced by a skill is stored under that skill's directory.

    The spec's skill directory holds the skill's `references/` too, not just
    its `SKILL.md`, so `multihost`'s `audit/severity` is sourced from
    `audit/references/severity.md`. The directory is read off the skill's own
    source rather than assumed, since a host only needs a `skills/` prefix when
    it has rules or agents to keep the skills apart from. A doc that belongs to
    no declared skill is exempt — there is no directory for it to live in.
    """
    directories = {
        source_name(source): SPEC.directory(source)
        for skill in host.skills
        for source in skill.sources
    }
    for doc in host.docs:
        owner, _, rest = doc.name.partition("/")
        if not rest or owner not in directories:
            continue
        assert doc.source.startswith(directories[owner] + "/"), (
            f"doc {doc.name!r} is sourced from {doc.source!r}, outside "
            f"the {directories[owner]!r} skill directory"
        )


def test_previous_names_are_validated() -> None:
    with pytest.raises(ValueError, match="lists 'x' as a previous name"):
        Host("d", "c", "p", artifacts=(Rule("x", "r.md", previous_names=("x",)),))
    with pytest.raises(ValueError, match="as a previous name"):
        Host("d", "c", "p", artifacts=(Rule("x", "r.md", previous_names=("",)),))
    with pytest.raises(ValueError, match="still installs under it"):
        Host(
            "d",
            "c",
            "p",
            artifacts=(
                Rule("old", "a.md"),
                Rule("new", "b.md", previous_names=("old",)),
            ),
        )
    # A previous name of one kind may still be a live name of another.
    Host(
        "d",
        "c",
        "p",
        artifacts=(
            Rule("shared", "a.md"),
            Agent("fresh", "b.md", previous_names=("shared",)),
        ),
    )


def test_lines_are_validated() -> None:
    from pkgskills.host import Line

    Host("d", "c", "p", lines=(Line(".gitattributes", "docs/x.md", "merge=union"),))
    assert Line(".gitattributes", "docs/x.md", "merge=union").text == (
        "docs/x.md merge=union"
    )
    with pytest.raises(ValueError, match="repo-relative"):
        Host("d", "c", "p", lines=(Line("/etc/x", "k", "v"),))
    with pytest.raises(ValueError, match="repo-relative"):
        Host("d", "c", "p", lines=(Line("", "k", "v"),))
    with pytest.raises(ValueError, match="one whitespace-free token"):
        Host("d", "c", "p", lines=(Line("f", "two words", "v"),))
    with pytest.raises(ValueError, match="one whitespace-free token"):
        Host("d", "c", "p", lines=(Line("f", "", "v"),))
    with pytest.raises(ValueError, match="has no value"):
        Host("d", "c", "p", lines=(Line("f", "k", "  "),))
    with pytest.raises(ValueError, match="duplicate line"):
        Host("d", "c", "p", lines=(Line("f", "k", "v"), Line("f", "k", "w")))
