"""Tests for the pure renderers: stubs, copies, stamps, and prompt bodies."""

from __future__ import annotations

import dataclasses
import re

import pytest
import yaml
from examplehost.cli import HOST as EXAMPLE
from multihost.cli import HOST as MULTI
from solohost.cli import HOST as SOLO

from pkgskills.frontmatter import split_frontmatter
from pkgskills.host import Agent, Host, Rule, Skill
from pkgskills.rendering import (
    doc_body,
    render,
    render_copy,
    render_prompt,
    render_stub,
    stub_frontmatter,
)
from pkgskills.spec import SpecError
from pkgskills.stamp import (
    NOTE,
    is_stamped,
    legacy_reason,
    mask_versions,
    place_stamp,
    render_comment_stamp,
    render_stamp,
    stamped_by,
    stamped_mode,
)

STAMP_KEYS = {
    "pkgskills-host",
    "pkgskills-host-version",
    "pkgskills-version",
    "pkgskills-mode",
    "pkgskills-note",
}


def _metadata(text: str) -> dict[str, str]:
    """``text``'s frontmatter ``metadata``, every scalar as written."""
    front, _ = split_frontmatter(text)
    assert front is not None
    return yaml.load(front.inner, Loader=yaml.BaseLoader).get("metadata", {})


def test_single_skill_stub_lifts_frontmatter_verbatim() -> None:
    front, _ = split_frontmatter(SOLO.read("use-solo/SKILL.md"))
    assert front is not None
    stub = render_stub(SOLO, SOLO.skills[0], "global")
    source_lines = front.raw.splitlines()[:-1]  # every line but the closing fence
    assert stub.startswith("\n".join(source_lines) + "\n")


def test_stub_carries_a_source_declared_version_verbatim() -> None:
    audit = next(skill for skill in MULTI.skills if skill.name == "audit")
    stub = render_stub(MULTI, audit, MULTI.default_mode)
    front, _ = split_frontmatter(stub)
    source, _ = split_frontmatter(MULTI.read("audit/SKILL.md"))
    assert front is not None and source is not None
    assert front.get("name") == "audit"  # the source keys still parse
    assert 'metadata:\n  version: "2.1"\n' in front.raw
    # Byte for byte: dropping the stamp's lines gives back the source's block.
    kept = [
        line
        for line in front.raw.splitlines(keepends=True)
        if not line.lstrip().startswith("pkgskills-")
    ]
    assert "".join(kept) == source.raw
    assert stub_frontmatter(MULTI, audit) == source.raw


def test_stub_from_a_versionless_source_holds_only_the_stamp() -> None:
    assert set(_metadata(render_stub(SOLO, SOLO.skills[0], "global"))) == STAMP_KEYS
    assert "metadata" not in SOLO.read("use-solo/SKILL.md")


def test_dispatcher_stub_holds_only_the_stamp() -> None:
    stub = render_stub(EXAMPLE, EXAMPLE.skills[0], "local")
    assert set(_metadata(stub)) == STAMP_KEYS


def _bundle_stub() -> str:
    """A dispatcher over one source declaring a version and one declaring none."""
    bundle = Skill(name="bundle", sources=("audit/SKILL.md", "tidy/SKILL.md"))
    host = dataclasses.replace(MULTI, artifacts=(bundle,))
    return render_stub(host, bundle, MULTI.default_mode)


def test_dispatcher_frontmatter_lifts_nothing_from_a_source_declaring_metadata() -> (
    None
):
    source, _ = split_frontmatter(MULTI.read("audit/SKILL.md"))
    assert source is not None and "metadata" in source.fields  # not vacuous
    stub = _bundle_stub()
    assert set(_metadata(stub)) == STAMP_KEYS
    assert '"2.1"' not in stub


def test_dispatcher_table_shows_a_source_version_and_no_fallback() -> None:
    tidy, _ = split_frontmatter(MULTI.read("tidy/SKILL.md"))
    assert tidy is not None and tidy.metadata_field("version") is None  # not vacuous
    rows = {
        line.split(" | ")[0]: line.split(" | ")[1]
        for line in _bundle_stub().splitlines()
        if line.startswith("| `")
    }
    assert rows == {"| `audit`": "2.1", "| `tidy`": ""}
    assert MULTI.version != "2.1"


def test_dispatcher_table_sits_above_the_slash_sentence() -> None:
    stub = render_stub(EXAMPLE, EXAMPLE.skills[0], "global")
    header = (
        "Subcommands (2):\n\n| Subcommand | Version | Description |\n|---|---|---|\n"
    )
    assert header in stub
    assert stub.index(header) < stub.index("These map to `/example add`")
    assert "examplehost skill --list" in stub
    assert "\n- `" not in stub


def test_a_single_source_stub_has_no_subcommand_table() -> None:
    assert "| Subcommand |" not in render_stub(SOLO, SOLO.skills[0], "global")
    audit = next(skill for skill in MULTI.skills if skill.name == "audit")
    stub = render_stub(MULTI, audit, MULTI.default_mode)
    assert "| Subcommand |" not in stub
    assert _metadata(stub)["version"] == "2.1"


@pytest.mark.parametrize(
    ("source", "row"),
    [
        ("# no block\n", "| `add` |  |  |\n"),
        ("---\ndescription: Do a|b.\n---\n", "| `add` |  | Do a\\|b. |\n"),
        ("---\ndescription: >\n  Two\n  lines.\n---\n", "| `add` |  | Two lines. |\n"),
        (
            '---\ndescription: D.\nmetadata:\n  version: "1|2"\n---\n',
            "| `add` | 1\\|2 | D. |\n",
        ),
    ],
)
def test_dispatcher_table_row_stays_one_row(monkeypatch, source: str, row: str) -> None:
    monkeypatch.setattr(Host, "read", lambda self, path: source)
    assert row in render_stub(EXAMPLE, EXAMPLE.skills[0], "global")


def test_mask_versions_leaves_a_dispatcher_table_version_alone() -> None:
    stub = _bundle_stub()
    assert "| `audit` | 2.1 |" in mask_versions(stub, MULTI)


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
    assert f"`{prefix} install{local}`" in stub
    assert "--force`" in stub  # only the warning about it, never a command
    assert f"{prefix} install{local} --force" not in stub


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
    assert "SKILL.md" not in stubs["audit"]


def test_dispatcher_stub_lists_subcommands_with_descriptions() -> None:
    stub = render_stub(EXAMPLE, EXAMPLE.skills[0], "local")
    assert stub.startswith('---\nname: "example"\ndescription: ')
    assert "Subcommands: add, close." in stub
    assert "\n| `add` |  | Add a thing. " in stub
    assert "\n| `close` |  | Close a thing when the work is done. " in stub
    assert "`/example add`, `/example close`" in stub
    assert "uv run examplehost skill <subcommand>" in stub
    assert "ADD-BODY-SENTINEL" not in stub


def test_dispatcher_description_can_be_supplied() -> None:
    skill = dataclasses.replace(EXAMPLE.skills[0], description="Custom\n  text")
    stub = render_stub(EXAMPLE, skill, "global")
    front, _ = split_frontmatter(stub)
    assert front is not None
    assert front.get("description") == "Custom text"


def test_stub_rejects_a_source_whose_name_disagrees() -> None:
    host = Host(
        dist="solohost",
        cli="solohost",
        prompts="solohost.prompts",
        version="1.0",
        artifacts=(Skill(name="wrong-name", sources=("use-solo/SKILL.md",)),),
    )
    with pytest.raises(ValueError, match="names 'use-solo'"):
        stub_frontmatter(host, host.skills[0])


def test_stamp_names_host_pkgskills_and_mode_as_quoted_strings() -> None:
    lines = render_stamp(EXAMPLE, "local").splitlines()
    assert lines[0] == 'pkgskills-host: "examplehost"'
    assert lines[1] == 'pkgskills-host-version: "1.2.3"'
    assert lines[2].startswith('pkgskills-version: "')
    assert lines[3] == 'pkgskills-mode: "local"'
    assert lines[4] == f'pkgskills-note: "{NOTE}"'
    text = render(EXAMPLE, EXAMPLE.rules[0], "local")
    assert stamped_by(text) == "examplehost"
    assert stamped_mode(text, EXAMPLE) == "local"
    assert stamped_mode(text, SOLO) is None
    assert "<!--" not in text


def test_a_stamp_in_the_body_or_missing_a_key_is_not_a_stamp() -> None:
    stamp = "\n".join(f"  {line}" for line in render_stamp(SOLO, "local").splitlines())
    quoted = f"---\nname: x\n---\n\nmetadata:\n{stamp}\n"
    assert not is_stamped(quoted, SOLO)
    assert stamped_by(quoted) is None
    whole = f"---\nmetadata:\n{stamp}\n---\n"
    assert is_stamped(whole, SOLO)
    for mangled in (
        whole.replace('"local"', '"weird"'),
        whole.replace("pkgskills-host-version", "host-version"),
        whole.replace("pkgskills-version", "version"),
    ):
        assert not is_stamped(mangled, SOLO)
        assert stamped_by(mangled) == "solohost"
    assert not is_stamped("---\n{not: [yaml\n---\n", SOLO)
    assert not is_stamped("---\nmetadata: text\n---\n", SOLO)


def test_stamped_by_names_a_host_still_writing_comments() -> None:
    comment = render_comment_stamp(EXAMPLE, "local")
    assert stamped_by(f"{comment}\n\nbody\n") == "examplehost"
    assert stamped_by(f"---\nname: x\n---\n\n{comment}\n") == "examplehost"


def test_the_comment_form_counts_only_as_a_whole_line() -> None:
    comment = render_comment_stamp(SOLO, "global")
    assert stamped_mode(f"{comment}\n", SOLO) == "global"
    assert legacy_reason(f"{comment}\n", SOLO) == (
        "stamped in an HTML comment by an earlier pkgskills; "
        "the stamp now lives in frontmatter"
    )
    for text in (
        f"{comment} and more\n",
        f"Files say {comment}\n",
        comment.replace("(mode=global)", "(mode=weird)") + "\n",
        comment.replace("; do not edit", "") + "\n",
    ):
        assert not is_stamped(text, SOLO), text
    # Named for the host: another dist's comment is not this host's.
    assert not is_stamped(f"{render_comment_stamp(EXAMPLE, 'local')}\n", SOLO)


@pytest.mark.parametrize(
    ("front", "expected"),
    [
        pytest.param(
            "",
            'metadata:\n  k: "v"\n',
            id="no block",
        ),
        pytest.param(
            "---\n---\n",
            'metadata:\n  k: "v"\n',
            id="empty block",
        ),
        pytest.param(
            "---\nname: x\n---\n",
            'name: x\nmetadata:\n  k: "v"\n',
            id="no metadata",
        ),
        pytest.param(
            '---\nmetadata:\n  a: "b"\nname: x\n---\n',
            'metadata:\n  a: "b"\n  k: "v"\nname: x\n',
            id="after the source's keys, before the next",
        ),
        pytest.param(
            '---\nname: x\nmetadata:\n    a: "b"\n---\n',
            'name: x\nmetadata:\n    a: "b"\n    k: "v"\n',
            id="the source's indent",
        ),
        pytest.param(
            '---\nmetadata:\n  a: "b"\n  # own note\n\n# about name\nname: x\n---\n',
            'metadata:\n  a: "b"\n  # own note\n  k: "v"\n\n# about name\nname: x\n',
            id="comments stay with what they describe",
        ),
        pytest.param(
            '---\n  name: x\n  metadata:\n    a: "b"\n  license: y\n---\n',
            '  name: x\n  metadata:\n    a: "b"\n    k: "v"\n  license: y\n',
            id="an indented block",
        ),
        pytest.param(
            '---\nmetadata: {a: "b"}\nname: x\n---\n',
            'metadata: {a: "b", k: "v"}\nname: x\n',
            id="flow",
        ),
        pytest.param(
            "---\nmetadata: {}\n---\n",
            'metadata: {k: "v"}\n',
            id="empty flow",
        ),
        pytest.param(
            '---\nmetadata: {a: "b",}\n---\n',
            'metadata: {a: "b",k: "v"}\n',
            id="flow with a trailing comma",
        ),
        pytest.param(
            '---\nmetadata: {\n  a: "b",\n}\n---\n',
            'metadata: {\n  a: "b",\n  k: "v",\n}\n',
            id="multi-line flow with a trailing comma",
        ),
        pytest.param(
            '---\nmetadata: {\n    a: "b"\n}\nname: x\n---\n',
            'metadata: {\n    a: "b",\n    k: "v"\n}\nname: x\n',
            id="multi-line flow owing a comma, at the source's indent",
        ),
        pytest.param(
            '---\nmetadata: {\n  a: "b" # one, two\n}\n---\n',
            'metadata: {\n  a: "b", # one, two\n  k: "v"\n}\n',
            id="multi-line flow, a comment's comma is not YAML's",
        ),
        pytest.param(
            "---\nmetadata: {\n  a: 1, # one\n}\n---\n",
            'metadata: {\n  a: 1, # one\n  k: "v",\n}\n',
            id="multi-line flow, a trailing comma before a comment",
        ),
        pytest.param(
            "---\nmetadata: {\n}\n---\n",
            'metadata: {\n  k: "v"\n}\n',
            id="empty multi-line flow",
        ),
        pytest.param(
            '---\nmetadata: {\n  a: "b"}\n---\n',
            'metadata: {\n  a: "b", k: "v"}\n',
            id="multi-line flow with the brace on the last key's line",
        ),
    ],
)
def test_place_stamp_keeps_the_source_block_and_adds_the_keys(
    front: str, expected: str
) -> None:
    placed = place_stamp(front, 'k: "v"', "\nbody\n")
    assert placed == f"---\n{expected}---\n\nbody\n"


@pytest.mark.parametrize(
    "front",
    [
        pytest.param("---\n{name: x}\n---\n", id="flow root"),
        pytest.param("---\n- a\n---\n", id="sequence root"),
        pytest.param("---\n{not: [yaml\n---\n", id="invalid"),
        pytest.param("---\nmetadata: text\n---\n", id="scalar metadata"),
        pytest.param("---\nmetadata:\nname: x\n---\n", id="null metadata"),
        pytest.param(
            '---\nx: &m\n  a: "b"\nmetadata: *m\n---\n',
            id="an alias, where the keys would reach the anchor's key too",
        ),
        pytest.param(
            "---\nmetadata:\n  a: |+\n    text\n\n---\n",
            id="a keep scalar, whose trailing blank line is its value",
        ),
    ],
)
def test_place_stamp_refuses_a_block_it_would_change(front: str) -> None:
    with pytest.raises(ValueError, match="cannot add the provenance stamp"):
        place_stamp(front, 'k: "v"', "body\n")


def test_a_block_closed_without_a_newline_still_ends_in_one() -> None:
    assert place_stamp("---\nname: x\n---", 'k: "v"', "body\n") == (
        '---\nname: x\nmetadata:\n  k: "v"\n---\n\nbody\n'
    )


def test_a_multi_line_flow_map_takes_the_whole_stamp_a_line_each() -> None:
    stamp = render_stamp(SOLO, "local")
    placed = place_stamp('---\nmetadata: {\n  version: "2"\n}\n---\n', stamp, "body\n")
    assert placed.startswith('---\nmetadata: {\n  version: "2",\n')
    assert "".join(f"  {line},\n" for line in stamp.splitlines()[:-1]) in placed
    assert f"  {stamp.splitlines()[-1]}\n}}\n---\n" in placed
    assert stamped_mode(placed, SOLO) == "local"
    masked = mask_versions(placed, SOLO)
    assert '  pkgskills-host-version: "*",\n  pkgskills-version: "*",\n' in masked
    assert '  version: "2",\n' in masked


def test_every_stamp_shape_masks_only_its_two_versions() -> None:
    stamp = render_stamp(SOLO, "local")
    block = place_stamp("---\nname: x\n---\n", stamp, "body\n")
    flow = place_stamp('---\nmetadata: {version: "2"}\n---\n', stamp, "body\n")
    assert 'pkgskills-host-version: "*"' in mask_versions(block, SOLO)
    assert 'pkgskills-version: "*"' in mask_versions(block, SOLO)
    assert 'pkgskills-mode: "local"' in mask_versions(block, SOLO)
    assert 'pkgskills-host: "solohost"' in mask_versions(block, SOLO)
    masked = mask_versions(flow, SOLO)
    assert 'pkgskills-host-version: "*", pkgskills-version: "*"' in masked
    assert 'version: "2"' in masked
    # Every other byte is kept, and a body quoting the keys is the body's text.
    quoted = block + 'pkgskills-version: "1.0"\n'
    assert mask_versions(quoted, SOLO).endswith('\npkgskills-version: "1.0"\n')
    # Another host's stamp, or none, is left alone.
    assert mask_versions(block, EXAMPLE) == block
    assert mask_versions("no block\n", SOLO) == "no block\n"


def test_mask_versions_treats_a_body_change_as_a_change() -> None:
    one = render(SOLO, SOLO.skills[0], "local")
    assert mask_versions(one + "x\n", SOLO) != mask_versions(one, SOLO)


@pytest.mark.parametrize(
    ("source", "rule"),
    [
        ("---\nmetadata:\n  pkgskills-host: x\n---\nbody\n", "metadata-key-reserved"),
        ("---\nmetadata:\n  pkgskills-later: x\n---\nbody\n", "metadata-key-reserved"),
        ("---\nmetadata: text\n---\nbody\n", "metadata-not-a-mapping"),
        ("---\n- a\n---\nbody\n", "frontmatter-invalid"),
        ("---\n{not: [yaml\n---\nbody\n", "frontmatter-invalid"),
    ],
)
def test_a_copy_source_that_cannot_take_the_stamp_is_refused(
    source: str, rule: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Host, "read", lambda self, name: source)
    with pytest.raises(SpecError, match=rule) as exc:
        render_copy(EXAMPLE, EXAMPLE.rules[0], "local")
    assert {v.rule for v in exc.value.violations} == {rule}
    # Printing does not stamp, so it still works, and a bad block is the source's.
    assert "body" in render_copy(EXAMPLE, EXAMPLE.rules[0], "local", stamp=False)


@pytest.mark.parametrize(
    "source",
    [
        "body\n",
        "---\n---\nbody\n",
        "---\n# only a note\n---\nbody\n",
        '---\npaths: ["src/**"]\n---\nbody\n',
        '---\nmetadata:\n  own: "x"\n---\nbody\n',
    ],
)
def test_a_copy_source_takes_the_stamp_whatever_block_it_has(
    source: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Host, "read", lambda self, name: source)
    text = render_copy(EXAMPLE, EXAMPLE.rules[0], "local")
    assert stamped_mode(text, EXAMPLE) == "local"
    assert text.endswith("body\n")
    if "paths" in source:
        assert 'paths: ["src/**"]\n' in text


def test_mask_versions_ignores_a_version_bump_but_not_a_mode_change() -> None:
    one = render(EXAMPLE, EXAMPLE.rules[0], "global")
    bumped = dataclasses.replace(EXAMPLE, version="9.9.9")
    two = render(bumped, bumped.rules[0], "global")
    assert one != two
    assert mask_versions(one, EXAMPLE) == mask_versions(two, EXAMPLE)
    other_mode = render(EXAMPLE, EXAMPLE.rules[0], "local")
    assert mask_versions(one, EXAMPLE) != mask_versions(other_mode, EXAMPLE)


def test_mask_versions_leaves_a_source_declared_version_alone() -> None:
    """A host bump masks; a source's own `metadata.version` has to drift."""
    audit = next(skill for skill in MULTI.skills if skill.name == "audit")
    one = render_stub(MULTI, audit, MULTI.default_mode)
    bumped = dataclasses.replace(MULTI, version="9.9.9")
    assert mask_versions(
        render_stub(bumped, audit, MULTI.default_mode), MULTI
    ) == mask_versions(one, MULTI)
    revised = one.replace('version: "2.1"', 'version: "2.2"')
    assert mask_versions(revised, MULTI) != mask_versions(one, MULTI)


def test_legacy_stamps_are_read_from_the_host_in_declared_order() -> None:
    first = re.compile(r"<!-- old (?P<mode>global|local) -->")
    second = re.compile(r"<!-- older (?P<mode>global|local) -->")
    host = dataclasses.replace(SOLO, legacy_stamps=(first, second))
    text = "<!-- older global -->\n<!-- old local -->\n"

    assert is_stamped(text, host)
    # The first entry that matches, wherever its line sits in the file.
    assert stamped_mode(text, host) == "local"
    assert legacy_reason(text, host) == (
        "stamped by solohost before it adopted pkgskills"
    )
    # The field is the host's: a host that declares nothing reads none of it.
    assert not is_stamped(text, SOLO)
    assert stamped_mode(text, SOLO) is None
    assert legacy_reason(text, SOLO) is None


def test_a_legacy_pattern_with_an_unset_mode_group_records_nothing() -> None:
    pattern = re.compile(r"<!-- old (?P<mode>local)?-->")
    host = dataclasses.replace(SOLO, legacy_stamps=(pattern,))
    assert stamped_mode("<!-- old local-->\n", host) == "local"
    assert not is_stamped("<!-- old -->\n", host)


def test_mask_versions_leaves_a_legacy_stamp_alone() -> None:
    pattern = re.compile(r"<!-- old \S+ (?P<mode>global|local) -->")
    host = dataclasses.replace(SOLO, legacy_stamps=(pattern,))
    text = "<!-- old 1.0 local -->\n"
    assert mask_versions(text, host) == text


def test_render_prompt_strips_frontmatter_and_renders_cli_on_request() -> None:
    text = "---\nname: x\n---\n\nRun `{cli} go`.\n\n"
    assert render_prompt(text) == "Run `{cli} go`.\n"
    assert render_prompt(text, "uv run x") == "Run `uv run x go`.\n"
    assert render_prompt("no frontmatter") == "no frontmatter\n"


def test_rule_copy_gains_a_block_for_the_stamp_and_renders_cli() -> None:
    text = render_copy(EXAMPLE, EXAMPLE.rules[0], "local")
    assert text.startswith('---\nmetadata:\n  pkgskills-host: "examplehost"\n')
    assert "`uv run examplehost validate`" in text
    assert "RULE-BODY-SENTINEL" in text
    plain = render_copy(EXAMPLE, EXAMPLE.rules[0], "local", stamp=False)
    assert "pkgskills-" not in plain
    assert plain.startswith("# Things in this repo")


def test_agent_copy_adds_the_stamp_after_its_own_keys() -> None:
    text = render_copy(EXAMPLE, EXAMPLE.agents[0], "global")
    front, body = split_frontmatter(text)
    assert front is not None
    assert front.get("name") == "example-reviewer"
    assert "Reviews one thing" in (front.get("description") or "")
    assert front.raw.index("name:") < front.raw.index("pkgskills-host:")
    assert set(_metadata(text)) == STAMP_KEYS
    assert "<!--" not in body
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


@pytest.mark.parametrize(
    "description",
    [
        None,
        "Run: now # keep this",
        "true",
        'It\'s "quoted"',
        "@start",
        "[a, b]",
        "C:\\temp",
    ],
)
def test_dispatcher_frontmatter_is_valid_yaml(description: str | None) -> None:
    skill = dataclasses.replace(EXAMPLE.skills[0], description=description)
    raw = stub_frontmatter(EXAMPLE, skill)
    parsed = yaml.safe_load("\n".join(raw.splitlines()[1:-1]))
    assert parsed["name"] == skill.name
    assert isinstance(parsed["description"], str)
    if description is not None:
        assert parsed["description"] == description


@pytest.mark.parametrize("description", ["", "   ", "x" * 1025])
def test_dispatcher_rejects_invalid_descriptions(description: str) -> None:
    skill = dataclasses.replace(EXAMPLE.skills[0], description=description)
    with pytest.raises(ValueError, match="description"):
        stub_frontmatter(EXAMPLE, skill)


def test_subcommand_description_preserves_trailing_hyphens(monkeypatch) -> None:
    monkeypatch.setattr(
        Host, "read", lambda self, source: "---\ndescription: 'Use --'\n---\n"
    )
    assert "| `add` |  | Use -- |\n" in render_stub(
        EXAMPLE, EXAMPLE.skills[0], "global"
    )


def test_a_rule_warns_that_install_overwrites_edits() -> None:
    """A rule has no body text saying so, unlike a stub."""
    assert f'pkgskills-note: "{NOTE}"' in render(EXAMPLE, EXAMPLE.rules[0], "local")


def test_a_stamp_without_the_note_still_counts_and_drifts() -> None:
    """The note is for readers. Losing it is a content change, not a foreign file."""
    text = render(EXAMPLE, EXAMPLE.rules[0], "local")
    stripped = text.replace(f'  pkgskills-note: "{NOTE}"\n', "")
    assert stripped != text
    assert is_stamped(stripped, EXAMPLE)
    assert mask_versions(stripped, EXAMPLE) != mask_versions(text, EXAMPLE)
