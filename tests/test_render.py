"""Tests for the pure renderers: stubs, copies, stamps, and prompt bodies."""

from __future__ import annotations

import dataclasses

import pytest
from examplehost.cli import HOST as EXAMPLE
from multihost.cli import HOST as MULTI
from solohost.cli import HOST as SOLO

from mli.frontmatter import split_frontmatter
from mli.host import Agent, Host, Rule, Skill
from mli.rendering import (
    doc_body,
    render,
    render_copy,
    render_prompt,
    render_stub,
    stub_frontmatter,
    with_metadata,
)
from mli.stamp import (
    mask_versions,
    mli_version,
    render_stamp,
    stamped_by,
    stamped_mode,
)


def test_single_skill_stub_lifts_frontmatter_verbatim() -> None:
    front, _ = split_frontmatter(SOLO.read("skills/use-solo/SKILL.md"))
    assert front is not None
    stub = render_stub(SOLO, SOLO.skills[0], "global")
    source_lines = front.raw.splitlines()[:-1]  # every line but the closing fence
    assert stub.startswith("\n".join(source_lines) + "\n")


def test_stub_declares_both_versions_as_metadata() -> None:
    stub = render_stub(SOLO, SOLO.skills[0], "global")
    front, _ = split_frontmatter(stub)
    assert front is not None
    assert front.get("name") == "use-solo"  # the source keys still parse
    assert '\nmetadata:\n  version: "0.9.0"\n  mli-version: "' in front.raw
    assert front.raw.endswith('"\n---\n')


def test_dispatcher_stub_declares_metadata_too() -> None:
    front, _ = split_frontmatter(render_stub(EXAMPLE, EXAMPLE.skills[0], "local"))
    assert front is not None
    assert 'metadata:\n  version: "1.2.3"\n' in front.raw


def test_stub_metadata_joins_a_metadata_block_the_source_declares() -> None:
    raw = "---\nname: x\nmetadata:\n  author: example-org\n---\n"
    out = with_metadata(raw, SOLO, SOLO.skills[0])
    assert out == (
        "---\nname: x\nmetadata:\n"
        f'  version: "0.9.0"\n  mli-version: "{mli_version()}"\n'
        "  author: example-org\n---\n"
    )


def test_stub_metadata_stops_scanning_at_the_next_top_level_key() -> None:
    raw = '---\nname: x\nmetadata:\n  author: example-org\nversion: "2.0"\n---\n'
    out = with_metadata(raw, SOLO, SOLO.skills[0])
    # A top-level `version` is a different key from `metadata.version`, so it
    # is neither a conflict nor moved.
    assert out.endswith('  author: example-org\nversion: "2.0"\n---\n')
    assert '  version: "0.9.0"\n' in out


def test_stub_metadata_rejects_a_source_that_claims_a_managed_key() -> None:
    raw = '---\nname: x\nmetadata:\n  version: "2.0"\n---\n'
    with pytest.raises(ValueError, match="already declares metadata.version"):
        with_metadata(raw, SOLO, SOLO.skills[0])


def test_single_skill_stub_holds_no_instructions() -> None:
    stub = render_stub(SOLO, SOLO.skills[0], "global")
    assert "SOLO-BODY-SENTINEL" not in stub
    assert len(stub) < 2000


@pytest.mark.parametrize(
    ("mode", "prefix"), [("global", "solohost"), ("local", "uv run solohost")]
)
def test_single_skill_stub_names_mode_correct_commands(mode: str, prefix: str) -> None:
    stub = render_stub(SOLO, SOLO.skills[0], mode)  # type: ignore[arg-type]
    assert f"\n{prefix} skill use-solo\n" in stub
    local = " --local" if mode == "local" else ""
    assert f"{prefix} install{local} --check" in stub
    assert f"{prefix} install{local} --force" in stub


def test_every_stub_on_a_multi_skill_host_names_its_own_body() -> None:
    # The nameless `<cli> skill` a solo host could get away with exits 1 here,
    # so each stub has to name the body it stands for. `audit` proves the name
    # comes from the skill, not from the source file's stem.
    # Rendered for the host's only mode, which is the only one it installs in.
    stubs = {
        skill.name: render_stub(MULTI, skill, MULTI.default_mode)
        for skill in MULTI.skills
    }
    assert "\nuv run multihost skill tidy\n" in stubs["tidy"]
    assert "\nuv run multihost skill audit\n" in stubs["audit"]
    assert "audit-body" not in stubs["audit"]


def test_dispatcher_stub_lists_subcommands_with_descriptions() -> None:
    stub = render_stub(EXAMPLE, EXAMPLE.skills[0], "local")
    assert stub.startswith("---\nname: example\ndescription: ")
    assert "Subcommands: add, close." in stub
    assert "- `add` - Add a thing." in stub
    assert "- `close` - Close a thing when the work is done." in stub
    assert "`/example add`, `/example close`" in stub
    assert "uv run examplehost skill <subcommand>" in stub
    assert "ADD-BODY-SENTINEL" not in stub


def test_dispatcher_description_can_be_supplied() -> None:
    skill = dataclasses.replace(EXAMPLE.skills[0], description="Custom\n  text")
    stub = render_stub(EXAMPLE, skill, "global")
    assert "description: Custom text\n" in stub


def test_stub_rejects_a_source_whose_name_disagrees() -> None:
    host = Host(
        dist="solohost",
        cli="solohost",
        prompts="solohost.prompts",
        version="1.0",
        artifacts=(Skill(name="wrong-name", sources=("skills/use-solo/SKILL.md",)),),
    )
    with pytest.raises(ValueError, match="names 'use-solo'"):
        stub_frontmatter(host, host.skills[0])


def test_stamp_names_host_mli_mode_and_repair() -> None:
    stamp = render_stamp(EXAMPLE, "local")
    assert stamp.startswith("<!-- generated by examplehost 1.2.3 via mli ")
    assert "(mode=local)" in stamp
    assert stamp.endswith("uv run examplehost install --local --force -->")
    assert stamped_by(stamp) == "examplehost"
    assert stamped_mode(stamp, EXAMPLE) == "local"
    assert stamped_mode(stamp, SOLO) is None


def test_mask_versions_ignores_a_version_bump_but_not_a_mode_change() -> None:
    one = render(EXAMPLE, EXAMPLE.rules[0], "global")
    bumped = dataclasses.replace(EXAMPLE, version="9.9.9")
    two = render(bumped, bumped.rules[0], "global")
    assert one != two
    assert mask_versions(one, EXAMPLE) == mask_versions(two, EXAMPLE)
    other_mode = render(EXAMPLE, EXAMPLE.rules[0], "local")
    assert mask_versions(one, EXAMPLE) != mask_versions(other_mode, EXAMPLE)


def test_mask_versions_covers_the_stubs_metadata_versions() -> None:
    one = render(EXAMPLE, EXAMPLE.skills[0], "global")
    bumped = dataclasses.replace(EXAMPLE, version="9.9.9")
    two = render(bumped, bumped.skills[0], "global")
    assert 'version: "9.9.9"' in two
    assert one != two
    assert mask_versions(one, EXAMPLE) == mask_versions(two, EXAMPLE)


def test_render_prompt_strips_frontmatter_and_renders_cli_on_request() -> None:
    text = "---\nname: x\n---\n\nRun `{cli} go`.\n\n"
    assert render_prompt(text) == "Run `{cli} go`.\n"
    assert render_prompt(text, "uv run x") == "Run `uv run x go`.\n"
    assert render_prompt("no frontmatter") == "no frontmatter\n"


def test_rule_copy_puts_stamp_first_and_renders_cli() -> None:
    text = render_copy(EXAMPLE, EXAMPLE.rules[0], "local")
    assert text.startswith("<!-- generated by examplehost 1.2.3")
    assert "`uv run examplehost validate`" in text
    assert "RULE-BODY-SENTINEL" in text
    plain = render_copy(EXAMPLE, EXAMPLE.rules[0], "local", stamp=False)
    assert "generated by" not in plain
    assert plain.startswith("# Things in this repo")


def test_agent_copy_keeps_frontmatter_then_stamp() -> None:
    text = render_copy(EXAMPLE, EXAMPLE.agents[0], "global")
    front, body = split_frontmatter(text)
    assert front is not None
    assert front.get("name") == "example-reviewer"
    assert "Reviews one thing" in (front.get("description") or "")
    assert body.lstrip("\n").startswith("<!-- generated by examplehost")
    assert "AGENT-BODY-SENTINEL" in body


def test_doc_body_renders_like_a_skill_body() -> None:
    fields = doc_body(MULTI, MULTI.doc("tidy/fields"), "local")
    assert fields.startswith("# Fields a tidy pass may rewrite\n")
    assert "uv run multihost install --check" in fields
    assert "generated by" not in fields
    # Frontmatter goes the same way it does on the skill path.
    severity = doc_body(MULTI, MULTI.doc("audit/severity"), "local")
    assert severity.startswith("# Severity\n")
    assert "description:" not in severity


def test_a_doc_that_opts_out_keeps_the_placeholder() -> None:
    literal = dataclasses.replace(MULTI.doc("tidy/fields"), render_cli=False)
    assert "{cli} install --check" in doc_body(MULTI, literal, "local")


def test_render_is_deterministic() -> None:
    for art in EXAMPLE.artifacts:
        assert render(EXAMPLE, art, "global") == render(EXAMPLE, art, "global")


def test_rule_and_agent_are_copies_not_stubs() -> None:
    assert isinstance(EXAMPLE.rules[0], Rule)
    assert isinstance(EXAMPLE.agents[0], Agent)
    assert "printed on demand" not in render(EXAMPLE, EXAMPLE.rules[0], "global")
