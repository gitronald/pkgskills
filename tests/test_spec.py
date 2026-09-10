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
    # Both broken skills are reported, not just the first.
    assert {v.where for v in found} == {"flat-skill.md", "misfiled/SKILL.md"}
    assert rules(found) == {
        "entry-file",  # flat-skill.md is not <name>/SKILL.md
        "description-missing",  # misfiled declares none
        "name-grammar",  # "Misfiled Skill" is not the grammar
        "name-matches-directory",  # ...and is not "misfiled" either
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
