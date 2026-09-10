"""Tests for the Agent Skills specification encoded in `mli.spec`.

`brokenhost` is the fixture with the failing cases in it; the other three are
exemplary and must stay silent under every check here.
"""

from __future__ import annotations

import dataclasses

import pytest
from examplehost.cli import HOST as EXAMPLE
from multihost.cli import HOST as MULTI
from solohost.cli import HOST as SOLO

from mli.frontmatter import Block, find_block, split_frontmatter
from mli.host import Doc, Host, Skill
from mli.spec import SPEC, SkillSpec, SpecError, Violation, report
from mli.testing import assert_spec_conformant

BROKEN = Host(
    dist="brokenhost",
    cli="brokenhost",
    prompts="brokenhost.prompts",
    version="0.0.1",
    artifacts=(
        Skill(name="flat-skill", sources=("flat-skill.md",)),
        Skill(name="misfiled", sources=("misfiled/SKILL.md",)),
        Skill(name="bad-metadata", sources=("bad-metadata/SKILL.md",)),
    ),
)


def rules(violations: list[Violation]) -> set[str]:
    return {v.rule for v in violations}


# -- the spec as data -------------------------------------------------------


def test_spec_carries_the_specs_own_fields_and_limits() -> None:
    assert SPEC.entry_file == "SKILL.md"
    assert SPEC.optional_dirs == ("scripts", "references", "assets")
    assert [f.name for f in SPEC.required_fields] == ["name", "description"]
    assert SPEC.field("name").max_length == 64
    assert SPEC.field("description").max_length == 1024
    assert SPEC.field("compatibility").max_length == 500
    # `license`, `metadata`, and `allowed-tools` are declared but unlimited.
    assert SPEC.field("license").max_length is None
    assert not SPEC.field("allowed-tools").required
    with pytest.raises(KeyError):
        SPEC.field("no-such-field")


def test_structure_renders_the_spec_diagram_for_an_error_to_quote() -> None:
    diagram = SPEC.structure("pdf-processing")
    assert diagram.startswith("pdf-processing/\n")
    assert "SKILL.md" in diagram
    for directory in SPEC.optional_dirs:
        assert f"{directory}/" in diagram


def test_the_spec_is_data_so_a_caller_can_pin_a_different_reading() -> None:
    strict = dataclasses.replace(SPEC, entry_file="skill.md")
    assert strict.is_entry("add/skill.md")
    assert not strict.is_entry("add/SKILL.md")
    # The shipped spec is untouched by that.
    assert SPEC.is_entry("add/SKILL.md")


# -- layout -----------------------------------------------------------------


def test_is_entry_and_directory_read_the_conformant_layout() -> None:
    assert SPEC.is_entry("add/SKILL.md")
    assert SPEC.is_entry("skills/add/SKILL.md")
    assert SPEC.directory("skills/add/SKILL.md") == "skills/add"
    # A bare SKILL.md has no directory to be named by, so it is not an entry.
    assert not SPEC.is_entry("SKILL.md")
    assert not SPEC.is_entry("add.md")
    assert SPEC.directory("add.md") == ""


def test_check_layout_reports_a_flat_source_with_the_diagram() -> None:
    assert SPEC.check_layout("add/SKILL.md") == []
    (violation,) = SPEC.check_layout("skills/add.md")
    assert violation.rule == "entry-file"
    assert "flat file" in violation.detail
    # The fix quotes the spec's own structure, so the author sees the target.
    assert "SKILL.md" in violation.fix
    assert "references/" in violation.fix


# -- names ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("pdf-processing", None),
        ("a1", None),
        ("", "it is empty"),
        ("a" * 65, "over the 64-character limit"),
        ("-pdf", "starts or ends with a hyphen"),
        ("pdf-", "starts or ends with a hyphen"),
        ("pdf--processing", "consecutive hyphens"),
        ("PDF-Processing", "uppercase"),
        ("pdf processing", "outside a-z, 0-9 and hyphens"),
        ("edit/refs", "outside a-z, 0-9 and hyphens"),
    ],
)
def test_name_problem_says_which_rule_was_broken(
    name: str, expected: str | None
) -> None:
    problem = SPEC.name_problem(name)
    if expected is None:
        assert problem is None
        assert SPEC.valid_name(name)
    else:
        assert problem is not None and expected in problem
        assert not SPEC.valid_name(name)


# -- frontmatter ------------------------------------------------------------


def test_check_frontmatter_reports_a_missing_block() -> None:
    (violation,) = SPEC.check_frontmatter("add/SKILL.md", "# add\n\nno block here\n")
    assert violation.rule == "frontmatter-missing"
    assert "name" in violation.fix and "description" in violation.fix


def test_check_frontmatter_reports_every_missing_required_field() -> None:
    found = SPEC.check_frontmatter("add/SKILL.md", "---\nlicense: MIT\n---\n\nbody\n")
    assert rules(found) == {"name-missing", "description-missing"}


def test_check_frontmatter_reports_over_length_fields() -> None:
    text = (
        "---\n"
        "name: add\n"
        f"description: {'x' * 1025}\n"
        f"compatibility: {'y' * 501}\n"
        "---\n\nbody\n"
    )
    found = SPEC.check_frontmatter("add/SKILL.md", text)
    assert rules(found) == {"description-too-long", "compatibility-too-long"}
    detail = next(v.detail for v in found if v.rule == "description-too-long")
    assert "1025 characters" in detail and "1024-character limit" in detail


def test_check_frontmatter_ties_the_name_to_the_directory() -> None:
    text = "---\nname: other\ndescription: A thing.\n---\n\nbody\n"
    (violation,) = SPEC.check_frontmatter("skills/add/SKILL.md", text)
    assert violation.rule == "name-matches-directory"
    assert "'other'" in violation.detail and "'add'" in violation.detail
    # `other` is a valid name, so either half of the mismatch may be fixed.
    assert (
        violation.fix == "rename the directory to 'other', or set the `name` to 'add'"
    )

    # A flat source has no directory to disagree with, so the rule is silent.
    assert SPEC.check_frontmatter("skills/add.md", text) == []


def test_a_blank_optional_field_is_not_reported() -> None:
    text = "---\nname: add\ndescription: A thing.\nlicense:\n---\n\nbody\n"
    assert SPEC.check_frontmatter("add/SKILL.md", text) == []


# -- whole hosts ------------------------------------------------------------


def test_check_skill_reads_each_source_and_reports_a_missing_one() -> None:
    host = dataclasses.replace(
        SOLO, artifacts=(Skill(name="gone", sources=("gone/SKILL.md",)),)
    )
    (violation,) = SPEC.check_skill(host, host.skills[0])
    assert violation.rule == "source-missing"
    assert "solohost.prompts" in violation.detail


def test_check_host_collects_every_violation_across_the_broken_fixture() -> None:
    found = BROKEN.check_spec()
    # Every broken skill is reported, not just the first.
    assert {v.where for v in found} == {
        "flat-skill.md",
        "misfiled/SKILL.md",
        "bad-metadata/SKILL.md",
    }
    assert rules(found) == {
        "entry-file",  # flat-skill.md is not <name>/SKILL.md
        "description-missing",  # misfiled declares none
        "name-grammar",  # "Misfiled Skill" is not the grammar
        "name-matches-directory",  # ...and is not "misfiled" either
        "metadata-value-not-a-string",  # bad-metadata's floats, ints and bools
    }


@pytest.mark.parametrize("host", [EXAMPLE, SOLO, MULTI], ids=lambda h: h.dist)
def test_the_exemplary_fixtures_are_conformant(host: Host) -> None:
    assert host.check_spec() == []
    assert_spec_conformant(host)


def test_assert_spec_conformant_names_the_rule_and_the_fix() -> None:
    with pytest.raises(AssertionError) as exc:
        assert_spec_conformant(BROKEN)
    message = str(exc.value)
    assert "brokenhost ships skills that do not follow" in message
    assert "skills-ref validate" in message
    # Grouped by file, each line naming its rule slug and its repair.
    assert "  misfiled/SKILL.md:" in message
    assert "[name-matches-directory]" in message
    # The `name` is itself ungrammatical, so the fix never advises renaming
    # the directory to it -- that would trade one violation for two.
    assert "-- set the `name` to 'misfiled'" in message
    assert "rename the directory to 'Misfiled Skill'" not in message


# -- how the failures surface ----------------------------------------------


def test_a_declared_name_the_spec_rejects_fails_at_construction() -> None:
    with pytest.raises(SpecError) as exc:
        Host(
            dist="d",
            cli="c",
            prompts="p",
            artifacts=(Skill("Bad", ("a.md",)), Skill("worse-", ("b.md",))),
        )
    # Both are reported, so an author fixing two names sees two.
    assert exc.value.violations[0].detail.startswith("skill name 'Bad'")
    assert exc.value.violations[1].detail.startswith("skill name 'worse-'")
    assert rules(list(exc.value.violations)) == {"name-grammar"}


def test_construction_does_not_read_sources() -> None:
    # Only names are checked on import; a source that does not exist is caught
    # by `check_spec`, not by declaring the host. Docs are the exception, and
    # keep being read.
    host = Host(dist="d", cli="c", prompts="solohost.prompts", artifacts=())
    assert host.check_spec() == []
    with pytest.raises(ValueError, match="no such prompt"):
        Host(
            dist="d",
            cli="c",
            prompts="solohost.prompts",
            docs=(Doc("x", "nope.md"),),
        )


def test_spec_error_keeps_the_violations_as_data() -> None:
    violations = [Violation("a.md", "some-rule", "it is wrong", "fix it")]
    err = SpecError(violations, header="broken:")
    assert err.violations == tuple(violations)
    assert str(err) == "broken:\n  a.md:\n    - it is wrong [some-rule] -- fix it"
    assert str(violations[0]) == "a.md: it is wrong [some-rule] -- fix it"


def test_report_groups_violations_by_file_in_first_seen_order() -> None:
    found = [
        Violation("b.md", "one", "d1", "f1"),
        Violation("a.md", "two", "d2", "f2"),
        Violation("b.md", "three", "d3", "f3"),
    ]
    lines = report(found, header="head:").splitlines()
    assert lines[0] == "head:"
    assert lines[1] == "  b.md:"
    assert [line.strip() for line in lines[2:4]] == [
        "- d1 [one] -- f1",
        "- d3 [three] -- f3",
    ]
    assert lines[4] == "  a.md:"


def test_a_custom_spec_flows_through_the_checks() -> None:
    lenient = SkillSpec(optional_dirs=("references",))
    assert "scripts/" not in lenient.structure()
    assert "references/" in lenient.check_layout("a.md")[0].fix


# -- metadata ---------------------------------------------------------------


def metadata_check(block: str) -> list[Violation]:
    text = f"---\nname: add\ndescription: A thing.\n{block}---\n\nbody\n"
    front, _ = split_frontmatter(text)
    assert front is not None
    return SPEC.check_metadata("add/SKILL.md", front)


def test_a_string_valued_metadata_mapping_is_accepted() -> None:
    # The spec's own example, quotes included.
    assert metadata_check('metadata:\n  author: example-org\n  version: "1.0"\n') == []
    # An unquoted plain scalar is still a string; only YAML's other resolutions
    # are the problem.
    assert metadata_check("metadata:\n  author: example-org\n") == []


def test_metadata_absent_is_not_a_violation() -> None:
    assert metadata_check("") == []


@pytest.mark.parametrize(
    ("value", "reads_as"),
    [
        ("1.0", "a float"),
        ("3", "an integer"),
        ("-2", "an integer"),
        ("1e6", "a float"),
        (".5", "a float"),
        ("true", "a boolean"),
        ("False", "a boolean"),
        ("yes", "a boolean"),
        ("off", "a boolean"),
        ("null", "a null"),
        ("~", "a null"),
    ],
)
def test_metadata_values_yaml_would_not_return_as_strings(
    value: str, reads_as: str
) -> None:
    (violation,) = metadata_check(f"metadata:\n  key: {value}\n")
    assert violation.rule == "metadata-value-not-a-string"
    assert f"which YAML reads as {reads_as}" in violation.detail
    assert violation.fix == f'quote it -- `key: "{value}"`'
    # Quoting it is the fix, and it works.
    assert metadata_check(f'metadata:\n  key: "{value}"\n') == []
    assert metadata_check(f"metadata:\n  key: '{value}'\n") == []


def test_metadata_must_be_a_mapping_not_a_scalar() -> None:
    (violation,) = metadata_check("metadata: whatever\n")
    assert violation.rule == "metadata-not-a-mapping"
    assert "'whatever'" in violation.detail


def test_metadata_that_opens_nothing_reads_back_as_null() -> None:
    (violation,) = metadata_check("metadata:\n")
    assert violation.rule == "metadata-not-a-mapping"
    assert "null" in violation.detail


def test_metadata_may_not_hold_a_sequence() -> None:
    # One violation for the whole block, not one per item.
    (violation,) = metadata_check("metadata:\n  - one\n  - two\n")
    assert violation.rule == "metadata-not-a-mapping"
    assert "'- one', '- two', which declares no key" in violation.detail


def test_a_nested_mapping_is_reported_against_the_key_that_opens_it() -> None:
    found = metadata_check("metadata:\n  owner:\n    team: platform\n")
    # One violation, not two: the deeper line is part of the value, not an
    # entry of its own.
    (violation,) = found
    assert violation.rule == "metadata-value-not-a-string"
    assert "`metadata.owner` has no scalar value" in violation.detail


def test_every_bad_value_is_reported_not_just_the_first() -> None:
    found = metadata_check("metadata:\n  a: 1\n  b: true\n  c: fine\n  d: 2.5\n")
    assert [v.detail.split("`")[1] for v in found] == [
        "metadata.a",
        "metadata.b",
        "metadata.d",
    ]


# -- the raw block helper ---------------------------------------------------


def block_of(raw: str) -> Block | None:
    return find_block(raw, "metadata")


def test_find_block_returns_none_when_the_key_is_absent() -> None:
    assert block_of("---\nname: add\n---\n") is None
    # An indented `metadata:` belongs to some other key, not the top level.
    assert block_of("---\nowner:\n  metadata: x\n---\n") is None


def test_find_block_keeps_blank_lines_inside_the_mapping() -> None:
    raw = "---\nmetadata:\n  a: 1\n\n  b: 2\nname: add\n---\n"
    block = block_of(raw)
    assert block is not None and block.at == 1
    # The gap does not truncate the block: `b` is still in it.
    assert [key for _, key, _ in block.entries()] == ["a", "b"]
    # ...and a trailing blank is not carried along.
    assert block.lines[-1].strip()


def test_block_entries_drop_blanks_and_comments_and_flag_non_pairs() -> None:
    raw = "---\nmetadata:\n  # a note\n  a: 1\n  - loose\n---\n"
    block = block_of(raw)
    assert block is not None
    assert block.entries() == [(2, "a", "1"), (2, "", "- loose")]


def test_find_block_reads_an_inline_scalar() -> None:
    block = block_of("---\nmetadata: scalar\nname: add\n---\n")
    assert block is not None
    assert block.inline == "scalar" and block.lines == []
