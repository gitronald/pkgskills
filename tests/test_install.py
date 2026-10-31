"""Tests for locating, writing, and drift-checking generated artifacts."""

from __future__ import annotations

import dataclasses
import os
from pathlib import Path

import pytest
from examplehost.cli import HOST as EXAMPLE
from multihost.cli import HOST as MULTI
from solohost.cli import HOST as SOLO

from pkgskills import artifacts as inst
from pkgskills.harness import CLAUDE_CODE, CODEX
from pkgskills.host import Host, Line, Mode
from pkgskills.rendering import render
from pkgskills.testing import Sandbox


def _statuses(host: Host, root: Path, mode: str | None = None) -> dict[str, str]:
    rows = inst.check(host, root, mode)  # type: ignore[arg-type]
    return {
        f"{row.harness.name}:{row.artifact.kind.value}:{row.artifact.name}": row.status
        for row in rows
    }


@pytest.fixture
def home_link(box: Sandbox, tmp_path: Path) -> Path:
    """A symlink to the sandbox's home directory."""
    link = tmp_path / "link"
    link.symlink_to(box.home)
    return link


@pytest.fixture
def no_home(monkeypatch: pytest.MonkeyPatch) -> None:
    """A machine where no home directory can be determined."""

    def raises() -> Path:
        raise RuntimeError("could not determine home directory")

    monkeypatch.setattr(inst, "global_base", raises)


def test_artifact_paths_per_mode_and_kind(box: Sandbox) -> None:
    skill, rule, agent = EXAMPLE.artifacts
    assert inst.artifact_path(EXAMPLE, skill, "global", box.repo, CLAUDE_CODE) == (
        box.home / ".claude/skills/example/SKILL.md"
    )
    assert inst.artifact_path(EXAMPLE, skill, "local", box.repo, CLAUDE_CODE) == (
        box.repo / ".claude/skills/example/SKILL.md"
    )
    assert inst.artifact_path(EXAMPLE, rule, "local", box.repo, CLAUDE_CODE) == (
        box.repo / ".claude/rules/examplehost.md"
    )
    assert inst.artifact_path(EXAMPLE, agent, "local", box.repo, CLAUDE_CODE) == (
        box.repo / ".claude/agents/example-reviewer.md"
    )


@pytest.mark.usefixtures("no_outer_markers")
def test_find_repo_root_walks_up_and_falls_back(box: Sandbox, tmp_path: Path) -> None:
    sub = box.repo / "a" / "b"
    sub.mkdir(parents=True)
    assert inst.find_repo_root(sub) == box.repo
    bare = tmp_path / "nowhere" / "deep"
    bare.mkdir(parents=True)
    assert inst.find_repo_root(bare) == bare
    claude_only = tmp_path / "c"
    (claude_only / ".claude").mkdir(parents=True)
    assert inst.find_repo_root(claude_only / "x", EXAMPLE.harnesses) == claude_only


def test_check_reports_missing_before_install(box: Sandbox) -> None:
    rows = inst.check(EXAMPLE, box.repo)
    assert {row.status for row in rows} == {"missing"}
    assert all(row.mode == "global" for row in rows)


def test_install_local_writes_every_artifact_then_checks_ok(box: Sandbox) -> None:
    report = inst.install(EXAMPLE, box.repo, "local")
    assert len(report.written) == 4
    assert all(p.is_file() and box.repo in p.parents for p in report.written)
    assert _statuses(EXAMPLE, box.repo, "local") == {
        "claude-code:skill:example": "ok",
        "codex:skill:example": "ok",
        "claude-code:rule:examplehost": "ok",
        "claude-code:agent:example-reviewer": "ok",
    }
    # Without a mode, check judges whatever is installed, and finds the same.
    assert set(_statuses(EXAMPLE, box.repo).values()) == {"ok"}
    assert all(row.mode == "local" for row in inst.check(EXAMPLE, box.repo))


def test_install_global_lives_under_home(box: Sandbox) -> None:
    report = inst.install(SOLO, box.repo, "global")
    assert report.written == (
        box.home / ".claude/skills/use-solo/SKILL.md",
        box.home / ".agents/skills/use-solo/SKILL.md",
    )
    assert inst.installed_mode(SOLO, box.repo) == "global"


def test_installed_mode_prefers_global(box: Sandbox) -> None:
    assert inst.installed_mode(SOLO, box.repo) is None
    inst.install(SOLO, box.repo, "local")
    assert inst.installed_mode(SOLO, box.repo) == "local"
    inst.install(SOLO, box.repo, "global")
    assert inst.installed_mode(SOLO, box.repo) == "global"


@pytest.mark.parametrize("modes", [("global", "local"), ("local", "global")])
def test_mode_preference_outranks_artifact_order(box: Sandbox, modes) -> None:
    host = dataclasses.replace(MULTI, modes=modes)
    inst.write_artifact(host, host.skills[0], modes[1], box.repo, CLAUDE_CODE)
    inst.write_artifact(host, host.skills[1], modes[0], box.repo, CLAUDE_CODE)
    assert inst.installed_mode(host, box.repo) == modes[0]
    assert inst.printing_mode(host, box.repo) == modes[0]


def test_harness_that_loads_both_skills_reports_no_shadow(box: Sandbox) -> None:
    host = dataclasses.replace(
        SOLO,
        harnesses=(dataclasses.replace(CLAUDE_CODE, shadowed_kinds=frozenset()), CODEX),
    )
    inst.install(host, box.repo, "global")
    assert inst.install(host, box.repo, "local").shadowed == ()


def test_printing_mode_folds_the_nothing_installed_case_into_a_default(
    box: Sandbox,
) -> None:
    # What `installed_mode` deliberately refuses to decide, exported for hosts
    # that print bodies of their own.
    assert inst.installed_mode(SOLO, box.repo) is None
    assert inst.printing_mode(SOLO, box.repo) == "global"
    assert inst.printing_mode(MULTI, box.repo) == "local"
    inst.install(SOLO, box.repo, "local")
    assert inst.printing_mode(SOLO, box.repo) == "local"


def test_docs_are_never_installed_or_checked(box: Sandbox) -> None:
    # multihost ships two docs; neither is written, and neither earns a row.
    report = inst.install(MULTI, box.repo, "local")
    assert len(report.written) == 2 * len(MULTI.artifacts)
    assert not (box.repo / ".claude/references").exists()
    assert set(_statuses(MULTI, box.repo)) == {
        "claude-code:skill:tidy",
        "codex:skill:tidy",
        "claude-code:skill:audit",
        "codex:skill:audit",
    }
    assert set(_statuses(MULTI, box.repo).values()) == {"ok"}


def test_version_only_bump_is_not_drift(box: Sandbox) -> None:
    inst.install(EXAMPLE, box.repo, "local")
    bumped = dataclasses.replace(EXAMPLE, version="1.3.0")
    assert set(_statuses(bumped, box.repo).values()) == {"ok"}


def test_moved_copy_is_judged_by_its_location(box: Sandbox) -> None:
    skill = SOLO.skills[0]
    path = inst.artifact_path(SOLO, skill, "global", box.repo, CLAUDE_CODE)
    path.parent.mkdir(parents=True)
    path.write_text(render(SOLO, skill, "local"), encoding="utf-8")
    row = inst.check_artifact(SOLO, skill, "global", box.repo, CLAUDE_CODE)
    assert row.status == "drifted"
    assert "mode=local" in row.reason


def test_hand_edited_body_is_drift(box: Sandbox) -> None:
    (path, codex_path) = inst.install(SOLO, box.repo, "local").written
    assert codex_path == box.repo / ".agents/skills/use-solo/SKILL.md"
    path.write_text(path.read_text() + "\nextra line\n", encoding="utf-8")
    row = inst.check(SOLO, box.repo)[0]
    assert row.status == "drifted"
    assert row.reason == "content differs from the current render"


def test_foreign_shapes(box: Sandbox) -> None:
    skill = SOLO.skills[0]
    path = inst.artifact_path(SOLO, skill, "local", box.repo, CLAUDE_CODE)
    path.parent.mkdir(parents=True)

    path.write_text("---\nname: use-solo\n---\nhand written\n", encoding="utf-8")
    row = inst.check_artifact(SOLO, skill, "local", box.repo, CLAUDE_CODE)
    assert (row.status, row.reason) == (
        "foreign",
        "no stamp; hand-written or from an older release",
    )

    path.write_text(
        "<!-- generated by otherpkg 1.0 via pkgskills 0.1 (mode=local) -->\n"
    )
    row = inst.check_artifact(SOLO, skill, "local", box.repo, CLAUDE_CODE)
    assert row.status == "foreign"
    assert row.reason == "generated by otherpkg, not solohost"

    # A stamp naming the host itself that pkgskills did not write. Still
    # foreign, but for its own reason -- and the reason claims only what the
    # line still records, since all three shapes below are indistinguishable
    # by then: a release predating adoption, a stamp a formatter line-wrapped,
    # and one whose mode token was corrupted.
    own = (
        "<!-- generated by solohost 1.0; do not edit -->\n",
        "<!-- generated by solohost 1.0\n via pkgskills 0.3.0 (mode=local) -->\n",
        "<!-- generated by solohost 1.0 via pkgskills 0.3.0 (mode=weird) -->\n",
    )
    for text in own:
        path.write_text(text)
        row = inst.check_artifact(SOLO, skill, "local", box.repo, CLAUDE_CODE)
        assert row.status == "foreign"
        assert row.reason == (
            "a solohost stamp pkgskills did not write; hand-edited, or from a "
            "release before solohost adopted pkgskills"
        )
        # The reason states the cause only; run_install appends the remedy.
        assert "--force" not in row.reason

    path.write_bytes(b"\xff\xfe\x00 not utf-8")
    assert inst.check_artifact(
        SOLO, skill, "local", box.repo, CLAUDE_CODE
    ).reason.startswith("unreadable")

    path.unlink()
    path.symlink_to(box.repo / "nowhere")
    row = inst.check_artifact(SOLO, skill, "local", box.repo, CLAUDE_CODE)
    assert (row.status, row.reason) == ("foreign", "a symlink, not a plain file")

    path.unlink()
    path.mkdir()
    row = inst.check_artifact(SOLO, skill, "local", box.repo, CLAUDE_CODE)
    assert (row.status, row.reason) == ("foreign", "a directory, not a file")


def test_prose_mention_of_the_marker_is_not_a_stamp(box: Sandbox) -> None:
    skill = SOLO.skills[0]
    path = inst.artifact_path(SOLO, skill, "local", box.repo, CLAUDE_CODE)
    path.parent.mkdir(parents=True)
    path.write_text(
        "Files say <!-- generated by solohost 1 via pkgskills 1 (mode=local) --> "
        "when generated.\n"
    )
    assert not inst.is_generated(path, SOLO)


def test_reinstall_over_own_copy_needs_no_force(box: Sandbox) -> None:
    inst.install(SOLO, box.repo, "local")
    inst.install(SOLO, box.repo, "local")
    assert _statuses(SOLO, box.repo) == {
        "claude-code:skill:use-solo": "ok",
        "codex:skill:use-solo": "ok",
    }


def test_foreign_target_is_refused_before_anything_is_written(box: Sandbox) -> None:
    rule_path = inst.artifact_path(
        EXAMPLE, EXAMPLE.rules[0], "local", box.repo, CLAUDE_CODE
    )
    rule_path.parent.mkdir(parents=True)
    rule_path.write_text("my own rule\n")
    with pytest.raises(inst.ForeignArtifactError) as excinfo:
        inst.install(EXAMPLE, box.repo, "local")
    assert excinfo.value.path == rule_path
    assert "no stamp" in excinfo.value.reason
    assert not inst.artifact_path(
        EXAMPLE, EXAMPLE.skills[0], "local", box.repo, CLAUDE_CODE
    ).exists()
    assert rule_path.read_text() == "my own rule\n"


def test_force_replaces_a_symlink_without_writing_through(box: Sandbox) -> None:
    target = box.repo / "elsewhere.md"
    target.write_text("untouched\n")
    path = inst.artifact_path(SOLO, SOLO.skills[0], "local", box.repo, CLAUDE_CODE)
    path.parent.mkdir(parents=True)
    path.symlink_to(target)
    with pytest.raises(inst.ForeignArtifactError):
        inst.install(SOLO, box.repo, "local")
    inst.install(SOLO, box.repo, "local", force=True)
    assert not path.is_symlink() and path.is_file()
    assert target.read_text() == "untouched\n"
    assert inst.is_generated(path, SOLO)


def test_global_install_removes_stale_local_copies_but_not_foreign_ones(
    box: Sandbox,
) -> None:
    inst.install(EXAMPLE, box.repo, "local")
    rule_local = inst.artifact_path(
        EXAMPLE, EXAMPLE.rules[0], "local", box.repo, CLAUDE_CODE
    )
    rule_local.write_text("hand edited, but keeps no stamp\n")
    report = inst.install(EXAMPLE, box.repo, "global")
    removed = set(report.removed)
    assert (
        inst.artifact_path(EXAMPLE, EXAMPLE.skills[0], "local", box.repo, CLAUDE_CODE)
        in removed
    )
    assert (
        inst.artifact_path(EXAMPLE, EXAMPLE.agents[0], "local", box.repo, CLAUDE_CODE)
        in removed
    )
    assert rule_local not in removed and rule_local.exists()


def test_local_install_reports_a_shadowing_global_copy(box: Sandbox) -> None:
    inst.install(SOLO, box.repo, "global")
    report = inst.install(SOLO, box.repo, "local")
    assert report.shadowed == (
        inst.artifact_path(SOLO, SOLO.skills[0], "local", box.repo, CLAUDE_CODE),
    )
    assert inst.shadowed_skills(SOLO, box.repo) == list(report.shadowed)


def test_check_without_mode_reports_both_locations(box: Sandbox) -> None:
    inst.install(SOLO, box.repo, "global")
    inst.install(SOLO, box.repo, "local")
    rows = inst.check(SOLO, box.repo)
    assert [(row.mode, row.harness) for row in rows] == [
        ("global", CLAUDE_CODE),
        ("global", CODEX),
        ("local", CLAUDE_CODE),
        ("local", CODEX),
    ]
    assert [row.status for row in rows] == ["ok", "ok", "ok", "stale"]


def test_local_copies_of_both_loading_kinds_go_stale_under_a_global_install(
    box: Sandbox,
) -> None:
    inst.install(EXAMPLE, box.repo, "local")
    # A global install of a *different* host leaves this one's local copies
    # alone, so install globally with the guard force-free: the local copies
    # this host generated are removed, then put back to model the leftover.
    written = inst.install(EXAMPLE, box.repo, "global").written
    assert written  # global copies now serve the repo
    for art in EXAMPLE.artifacts:
        local = inst.artifact_path(EXAMPLE, art, "local", box.repo, CLAUDE_CODE)
        local.parent.mkdir(parents=True, exist_ok=True)
        local.write_text(render(EXAMPLE, art, "local"), encoding="utf-8")

    found = inst.check(EXAMPLE, box.repo)
    rows = {(row.artifact.kind.value, row.mode): row for row in found}
    assert rows[("rule", "local")].status == "stale"
    assert rows[("agent", "local")].status == "stale"
    assert "remove it" in rows[("rule", "local")].reason
    # A skill's global copy shadows the local one, so the leftover is inert.
    assert rows[("skill", "local")].status == "ok"
    # Global copies are shared infrastructure and are never flagged.
    assert all(rows[(kind, "global")].status == "ok" for kind in ("skill", "rule"))


def test_a_superseded_local_copy_is_stale_even_when_its_content_drifted(
    box: Sandbox,
) -> None:
    # Removal is the remedy either way, so the leftover's content is beside the
    # point: reporting `drifted` would send the user to a reinstall that
    # recreates the very file they were told to delete.
    inst.install(EXAMPLE, box.repo, "global")
    rule = EXAMPLE.rules[0]
    local = inst.artifact_path(EXAMPLE, rule, "local", box.repo, CLAUDE_CODE)
    local.parent.mkdir(parents=True, exist_ok=True)
    local.write_text(
        render(EXAMPLE, rule, "local") + "\nhand-edited\n", encoding="utf-8"
    )

    row = inst.check_artifact(EXAMPLE, rule, "local", box.repo, CLAUDE_CODE)
    assert row.status == "stale"
    assert "remove it" in row.reason


def test_a_foreign_local_file_is_never_called_stale(box: Sandbox) -> None:
    inst.install(EXAMPLE, box.repo, "global")
    rule = EXAMPLE.rules[0]
    local = inst.artifact_path(EXAMPLE, rule, "local", box.repo, CLAUDE_CODE)
    local.parent.mkdir(parents=True, exist_ok=True)
    local.write_text("someone else's file\n", encoding="utf-8")
    assert (
        inst.check_artifact(EXAMPLE, rule, "local", box.repo, CLAUDE_CODE).status
        == "foreign"
    )


def test_check_resolves_the_installed_mode_once_for_the_whole_run(
    box: Sandbox, monkeypatch: pytest.MonkeyPatch
) -> None:
    inst.install(EXAMPLE, box.repo, "global")
    calls: list[Path] = []
    real = inst.installed_mode

    def counted(host: Host, root: Path) -> str | None:
        calls.append(root)
        return real(host, root)

    monkeypatch.setattr(inst, "installed_mode", counted)
    inst.check(EXAMPLE, box.repo)
    assert calls == [box.repo]


def test_stale_local_accepts_a_precomputed_installed_mode(box: Sandbox) -> None:
    rule = EXAMPLE.rules[0]
    inst.write_artifact(EXAMPLE, rule, "global", box.repo, CLAUDE_CODE)
    # No skill is on disk, so the resolved mode is None; the caller's handed-in
    # verdict is what decides, and "auto" re-derives it.
    assert inst.stale_local(
        EXAMPLE, rule, "local", box.repo, CLAUDE_CODE, installed="global"
    )
    assert not inst.stale_local(
        EXAMPLE, rule, "local", box.repo, CLAUDE_CODE, installed=None
    )
    assert not inst.stale_local(EXAMPLE, rule, "local", box.repo, CLAUDE_CODE)


def test_local_only_copies_are_not_stale(box: Sandbox) -> None:
    inst.install(EXAMPLE, box.repo, "local")
    assert set(_statuses(EXAMPLE, box.repo).values()) == {"ok"}
    assert not inst.stale_local(
        EXAMPLE, EXAMPLE.rules[0], "local", box.repo, CLAUDE_CODE
    )


def test_stale_needs_a_resolved_global_install_not_a_default(box: Sandbox) -> None:
    # Nothing installed anywhere: `installed_mode` is None, not "global".
    assert inst.installed_mode(EXAMPLE, box.repo) is None
    assert not inst.stale_local(
        EXAMPLE, EXAMPLE.rules[0], "local", box.repo, CLAUDE_CODE
    )


def test_no_stale_verdict_when_repo_root_is_home(box: Sandbox) -> None:
    os.chdir(box.home)
    (box.home / ".git").mkdir()
    inst.install(EXAMPLE, box.home, "global")
    # The two paths coincide, so there is one file, not a leftover second one.
    for art in EXAMPLE.artifacts:
        assert not inst.stale_local(EXAMPLE, art, "local", box.home, CLAUDE_CODE)


def test_installed_mode_falls_back_to_other_kinds_for_a_skill_less_host(
    box: Sandbox,
) -> None:
    rules_only = dataclasses.replace(EXAMPLE, artifacts=(EXAMPLE.rules[0],))
    assert inst.installed_mode(rules_only, box.repo) is None
    inst.install(rules_only, box.repo, "global")
    assert inst.installed_mode(rules_only, box.repo) == "global"


def test_a_local_only_host_never_resolves_or_writes_a_global_install(
    box: Sandbox,
) -> None:
    skill = MULTI.skills[0]
    inst.install(MULTI, box.repo, "local")
    assert inst.installed_mode(MULTI, box.repo) == "local"
    # A stray global copy is outside the host's world: it neither resolves as
    # the installed mode nor supersedes the per-repo one.
    stray = inst.artifact_path(MULTI, skill, "global", box.repo, CLAUDE_CODE)
    stray.parent.mkdir(parents=True)
    stray.write_text(render(MULTI, skill, "global"), encoding="utf-8")
    assert inst.installed_mode(MULTI, box.repo) == "local"
    assert inst.shadowed_skills(MULTI, box.repo) == []


def test_a_local_copy_is_never_stale_for_a_host_with_no_global_mode(
    box: Sandbox,
) -> None:
    # A rule, since a skill is shadowed rather than stale, and a host that
    # loads it from both bases but installs in only one of them.
    local_only = dataclasses.replace(EXAMPLE, modes=("local",))
    rule = local_only.rules[0]
    inst.install(local_only, box.repo, "local")
    assert not inst.stale_local(local_only, rule, "local", box.repo, CLAUDE_CODE)
    # Even handed a global verdict outright: there is no global install of this
    # host for a per-repo copy to be leftovers from.
    assert not inst.stale_local(
        local_only, rule, "local", box.repo, CLAUDE_CODE, installed="global"
    )
    inst.write_artifact(EXAMPLE, rule, "global", box.repo, CLAUDE_CODE)
    assert inst.stale_local(
        EXAMPLE, rule, "local", box.repo, CLAUDE_CODE, installed="global"
    )


def test_check_on_a_local_only_host_judges_the_repo_alone(box: Sandbox) -> None:
    rows = inst.check(MULTI, box.repo)
    assert {row.mode for row in rows} == {"local"}
    assert {row.status for row in rows} == {"missing"}
    inst.install(MULTI, box.repo, "local")
    rows = inst.check(MULTI, box.repo)
    assert {row.mode for row in rows} == {"local"}
    assert {row.status for row in rows} == {"ok"}


def test_installing_a_local_only_host_globally_is_refused(box: Sandbox) -> None:
    with pytest.raises(ValueError, match="does not install in global mode"):
        inst.install(MULTI, box.repo, "global")
    assert not (box.home / ".claude").exists()


def test_after_install_hook_receives_the_report(box: Sandbox) -> None:
    seen: list[inst.InstallReport] = []
    host = dataclasses.replace(SOLO, after_install=seen.append)
    report = inst.install(host, box.repo, "local")
    assert seen == [report]
    assert report.mode == "local" and report.root == box.repo


def test_after_install_hook_sees_force(box: Sandbox) -> None:
    seen: list[inst.InstallReport] = []
    host = dataclasses.replace(SOLO, after_install=seen.append)
    inst.install(host, box.repo, "local")
    inst.install(host, box.repo, "local", force=True)
    assert [report.force for report in seen] == [False, True]


def test_no_stale_removal_when_repo_root_is_home(box: Sandbox) -> None:
    os.chdir(box.home)
    (box.home / ".git").mkdir()
    # Written directly, since a local install at home is refused.
    inst.write_artifact(SOLO, SOLO.skills[0], "local", box.home, CLAUDE_CODE)
    report = inst.install(SOLO, box.home, "global")
    assert report.removed == ()
    assert inst.artifact_path(
        SOLO, SOLO.skills[0], "global", box.home, CLAUDE_CODE
    ).exists()


def test_a_global_install_keeps_its_files_under_a_symlinked_home(
    box: Sandbox, home_link: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The root is resolved and the global base is not, so comparing built paths
    # took the file just written for a leftover local copy and deleted it.
    (box.home / ".git").mkdir()
    monkeypatch.setenv("HOME", str(home_link))
    monkeypatch.chdir(home_link)
    root = inst.find_repo_root(harnesses=SOLO.harnesses)
    assert root == box.home

    report = inst.install(SOLO, root, "global")
    assert report.removed == ()
    assert all(path.is_file() for path in report.written)
    assert {row.status for row in inst.check(SOLO, root)} == {"ok"}


def test_root_is_home(box: Sandbox, home_link: Path) -> None:
    assert inst.root_is_home(box.home)
    assert not inst.root_is_home(box.repo)
    assert inst.root_is_home(home_link)


@pytest.mark.usefixtures("no_home")
def test_root_is_home_is_false_where_no_home_can_be_determined(box: Sandbox) -> None:
    assert not inst.root_is_home(box.home)


def test_local_install_at_home_is_refused_before_any_write(box: Sandbox) -> None:
    with pytest.raises(ValueError, match="same files"):
        inst.install(EXAMPLE, box.home, "local")
    assert not (box.home / ".claude").exists()


def test_a_local_only_host_keeps_its_one_location_at_home(box: Sandbox) -> None:
    assert inst.location_modes(MULTI, box.home) == ("local",)
    report = inst.install(MULTI, box.home, "local")
    assert report.written
    assert {row.status for row in inst.check(MULTI, box.home)} == {"ok"}


def test_a_local_first_host_at_home_resolves_to_global(box: Sandbox) -> None:
    host = dataclasses.replace(SOLO, modes=("local", "global"))
    assert inst.printing_mode(host, box.home) == "global"
    rows = inst.check(host, box.home)
    assert {(row.mode, row.status) for row in rows} == {("global", "missing")}

    inst.install(host, box.home, "global")
    assert inst.installed_mode(host, box.home) == "global"
    assert {(r.mode, r.status) for r in inst.check(host, box.home)} == {
        ("global", "ok")
    }


def test_stub_paths_at_home_list_each_file_once(box: Sandbox) -> None:
    rows = inst.skill_stub_paths(SOLO, box.home)
    assert [path for *_, path in rows] == [
        box.home / ".claude/skills/use-solo/SKILL.md",
        box.home / ".agents/skills/use-solo/SKILL.md",
    ]


# -- lines -------------------------------------------------------------------

ATTR = Line(".gitattributes", "docs/README.md", "merge=union")
LINED = dataclasses.replace(SOLO, lines=(ATTR,))


def test_line_statuses(box: Sandbox) -> None:
    path = box.repo / ".gitattributes"
    assert inst.check_line(ATTR, box.repo).status == "missing"

    path.write_text("*.png binary\n")
    assert inst.check_line(ATTR, box.repo).status == "missing"

    path.write_text("*.png binary\ndocs/README.md   merge=union  \n")
    assert inst.check_line(ATTR, box.repo).status == "ok"

    path.write_text("docs/README.md merge=ours\n")
    row = inst.check_line(ATTR, box.repo)
    assert (row.status, row.found) == ("drifted", "docs/README.md merge=ours")

    # The last line naming the key is the one git obeys.
    path.write_text(
        "docs/README.md merge=union\n# comment\ndocs/README.md merge=ours\n"
    )
    assert inst.check_line(ATTR, box.repo).status == "drifted"
    path.write_text("docs/README.md merge=ours\ndocs/README.md merge=union\n")
    assert inst.check_line(ATTR, box.repo).status == "ok"

    path.write_bytes(b"\xff\xfe not utf-8")
    assert inst.check_line(ATTR, box.repo).status == "unreadable"
    path.unlink()
    path.mkdir()
    assert inst.check_line(ATTR, box.repo).status == "unreadable"


def test_install_appends_a_missing_line_and_keeps_the_rest(box: Sandbox) -> None:
    path = box.repo / ".gitattributes"
    report = inst.install(LINED, box.repo, "local")
    (done,) = report.lines
    assert done.written and done.check.status == "missing"
    assert path.read_text() == "docs/README.md merge=union\n"

    path.write_text("*.png binary")  # no trailing newline
    report = inst.install(LINED, box.repo, "local")
    assert report.lines[0].written
    assert path.read_text() == "*.png binary\ndocs/README.md merge=union\n"

    report = inst.install(LINED, box.repo, "local")
    assert not report.lines[0].written and report.lines[0].check.ok
    assert inst.check_lines(LINED, box.repo)[0].ok


def test_a_line_is_read_once_per_write(
    box: Sandbox, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = box.repo / ".gitattributes"
    reads: list[Path] = []
    real = inst.read_plain

    def counting(target: Path) -> str | None:
        reads.append(target)
        return real(target)

    monkeypatch.setattr(inst, "read_plain", counting)
    # Absent, then present without the line, then drifted under force: the
    # edit works on the text the verdict came from, never a second read.
    inst.write_line(ATTR, box.repo)
    path.write_text("*.png binary\n")
    inst.write_line(ATTR, box.repo)
    path.write_text("docs/README.md merge=ours\n")
    inst.write_line(ATTR, box.repo, force=True)
    assert reads == [path, path]
    assert path.read_text() == "docs/README.md merge=union\n"


def test_a_line_lives_in_the_repo_whatever_the_mode(box: Sandbox) -> None:
    inst.install(LINED, box.repo, "global")
    assert (box.repo / ".gitattributes").read_text() == "docs/README.md merge=union\n"
    assert not (box.home / ".gitattributes").exists()


def test_a_drifted_line_is_rewritten_only_under_force(box: Sandbox) -> None:
    path = box.repo / ".gitattributes"
    path.write_text("*.png binary\ndocs/README.md merge=ours\n*.md text\n")
    report = inst.install(LINED, box.repo, "local")
    (done,) = report.lines
    assert not done.written and done.check.status == "drifted"
    assert "merge=ours" in path.read_text()

    report = inst.install(LINED, box.repo, "local", force=True)
    assert report.lines[0].written
    assert path.read_text() == "*.png binary\ndocs/README.md merge=union\n*.md text\n"


def test_an_unreadable_line_file_is_never_rewritten(box: Sandbox) -> None:
    path = box.repo / ".gitattributes"
    path.write_bytes(b"\xff\xfe not utf-8")
    for force in (False, True):
        report = inst.install(LINED, box.repo, "local", force=force)
        (done,) = report.lines
        assert not done.written and done.check.status == "unreadable"
        assert path.read_bytes() == b"\xff\xfe not utf-8"


# -- previous names ----------------------------------------------------------


def _renamed(host: Host) -> Host:
    """``host`` with its rule renamed, the old name declared as previous."""
    rule = host.rules[0]
    new = dataclasses.replace(rule, name="fresh", previous_names=(rule.name,))
    return dataclasses.replace(
        host, artifacts=tuple(new if art is rule else art for art in host.artifacts)
    )


def test_install_removes_a_stamped_file_at_a_previous_name(box: Sandbox) -> None:
    inst.install(EXAMPLE, box.repo, "local")
    old = inst.artifact_path(EXAMPLE, EXAMPLE.rules[0], "local", box.repo, CLAUDE_CODE)
    assert old.exists()
    renamed = _renamed(EXAMPLE)
    rows = {row.path: row for row in inst.check(renamed, box.repo)}
    assert rows[old].status == "stale"
    assert "previous name 'examplehost'" in rows[old].reason

    report = inst.install(renamed, box.repo, "local")
    assert report.renamed == (old,) and report.leftover == ()
    assert not old.exists()
    assert (box.repo / ".claude/rules/fresh.md").is_file()
    assert all(row.ok for row in inst.check(renamed, box.repo))
    # Nothing left to remove the second time.
    assert inst.install(renamed, box.repo, "local").renamed == ()


def test_an_unstamped_file_at_a_previous_name_survives(box: Sandbox) -> None:
    renamed = _renamed(EXAMPLE)
    old = box.repo / ".claude/rules/examplehost.md"
    old.parent.mkdir(parents=True)
    old.write_text("my own rule\n")
    report = inst.install(renamed, box.repo, "local")
    assert report.renamed == () and report.leftover == (old,)
    assert old.read_text() == "my own rule\n"
    # No row for it: it is not ours, so it neither gates nor drifts.
    assert old not in {row.path for row in inst.check(renamed, box.repo)}
    assert inst.leftover_previous(renamed, "local", box.repo) == [old]


def test_leftovers_are_read_once_each(
    box: Sandbox, monkeypatch: pytest.MonkeyPatch
) -> None:
    renamed = _renamed(EXAMPLE)
    old = box.repo / ".claude/rules/examplehost.md"
    old.parent.mkdir(parents=True)
    old.write_text("my own rule\n")
    reads: list[Path] = []
    real = inst.read_plain
    monkeypatch.setattr(inst, "read_plain", lambda p: (reads.append(p), real(p))[1])
    assert inst.leftover_previous(renamed, "local", box.repo) == [old]
    assert reads.count(old) == 1


def test_previous_names_are_cleaned_in_the_install_mode_only(box: Sandbox) -> None:
    inst.install(EXAMPLE, box.repo, "global")
    old = inst.artifact_path(EXAMPLE, EXAMPLE.rules[0], "global", box.repo, CLAUDE_CODE)
    renamed = _renamed(EXAMPLE)
    inst.install(renamed, box.repo, "local")
    assert old.exists()
    report = inst.install(renamed, box.repo, "global")
    assert report.renamed == (old,)


def test_a_renamed_skill_takes_its_empty_directory_with_it(box: Sandbox) -> None:
    inst.install(EXAMPLE, box.repo, "local")
    old = inst.artifact_path(EXAMPLE, EXAMPLE.skills[0], "local", box.repo, CLAUDE_CODE)
    # The dispatcher: it generates its own frontmatter, so the declaration
    # alone renames it. A single-source stub lifts the source's `name`.
    skill = dataclasses.replace(
        EXAMPLE.skills[0], name="fresh", previous_names=("example",)
    )
    renamed = dataclasses.replace(EXAMPLE, artifacts=(skill, *EXAMPLE.artifacts[1:]))
    inst.install(renamed, box.repo, "local")
    assert not old.parent.exists()
    # A directory that still holds something is left standing.
    inst.install(EXAMPLE, box.repo, "local")
    (old.parent / "notes.md").write_text("mine\n")
    inst.install(renamed, box.repo, "local")
    assert not old.exists() and (old.parent / "notes.md").exists()


def test_install_report_carries_the_previous_mode(box: Sandbox) -> None:
    assert inst.install(SOLO, box.repo, "local").previous is None
    assert inst.install(SOLO, box.repo, "local").previous == "local"
    assert inst.install(SOLO, box.repo, "global").previous == "local"
    assert inst.install(SOLO, box.repo, "global").previous == "global"


@pytest.mark.parametrize("mode", ["global", "local"])
def test_example_installs_only_supported_kinds_with_identical_stubs(
    box: Sandbox, mode: Mode
) -> None:
    base = box.home if mode == "global" else box.repo
    report = inst.install(EXAMPLE, box.repo, mode)
    assert report.written == (
        base / ".claude/skills/example/SKILL.md",
        base / ".agents/skills/example/SKILL.md",
        base / ".claude/rules/examplehost.md",
        base / ".claude/agents/example-reviewer.md",
    )
    assert report.written[0].read_bytes() == report.written[1].read_bytes()
    assert sorted(p.relative_to(base).as_posix() for p in base.rglob("*.md")) == [
        ".agents/skills/example/SKILL.md",
        ".claude/agents/example-reviewer.md",
        ".claude/rules/examplehost.md",
        ".claude/skills/example/SKILL.md",
    ]
    assert [
        (r.harness, r.mode, r.path, r.status) for r in inst.check(EXAMPLE, box.repo)
    ] == [
        (CLAUDE_CODE, mode, report.written[0], "ok"),
        (CODEX, mode, report.written[1], "ok"),
        (CLAUDE_CODE, mode, report.written[2], "ok"),
        (CLAUDE_CODE, mode, report.written[3], "ok"),
    ]


def test_check_reports_missing_per_harness(box: Sandbox) -> None:
    skill = SOLO.skills[0]
    path = inst.write_artifact(SOLO, skill, "local", box.repo, CLAUDE_CODE)
    assert [
        (r.harness, r.mode, r.path, r.status) for r in inst.check(SOLO, box.repo)
    ] == [
        (CODEX, "global", box.home / ".agents/skills/use-solo/SKILL.md", "missing"),
        (CLAUDE_CODE, "local", path, "ok"),
    ]


def test_codex_leftover_is_stale_removed_and_never_shadowed(box: Sandbox) -> None:
    skill = SOLO.skills[0]
    inst.install(SOLO, box.repo, "global")
    claude = inst.write_artifact(SOLO, skill, "local", box.repo, CLAUDE_CODE)
    codex = inst.write_artifact(SOLO, skill, "local", box.repo, CODEX)
    row = inst.check_artifact(SOLO, skill, "local", box.repo, CODEX)
    assert (row.harness, row.path, row.status) == (CODEX, codex, "stale")
    assert inst.shadowed_skills(SOLO, box.repo) == [claude]
    assert inst.remove_stale_local(SOLO, box.repo) == [claude, codex]
    assert not codex.exists()


def test_local_codex_copy_is_not_stale_without_a_global_codex_copy(
    box: Sandbox,
) -> None:
    skill = SOLO.skills[0]
    inst.install(SOLO, box.repo, "global")
    inst.artifact_path(SOLO, skill, "global", box.repo, CODEX).unlink()
    local = inst.write_artifact(SOLO, skill, "local", box.repo, CODEX)
    assert inst.installed_mode(SOLO, box.repo) == "global"
    row = next(row for row in inst.check(SOLO, box.repo) if row.path == local)
    assert row.status == "ok"


def test_foreign_codex_target_is_refused_before_any_write(box: Sandbox) -> None:
    path = box.repo / ".agents/skills/example/SKILL.md"
    path.parent.mkdir(parents=True)
    path.write_text("my own skill\n")
    with pytest.raises(inst.ForeignArtifactError) as excinfo:
        inst.install(EXAMPLE, box.repo, "local")
    assert excinfo.value.path == path
    assert path.read_text() == "my own skill\n"
    assert not (box.repo / ".claude").exists()
    assert not (box.home / ".agents").exists()


def test_find_repo_root_stops_at_codex_directory(box: Sandbox) -> None:
    inner = box.repo / "inner"
    (inner / ".codex").mkdir(parents=True)
    sub = inner / "a" / "b"
    sub.mkdir(parents=True)
    assert inst.find_repo_root(sub, EXAMPLE.harnesses) == inner
    assert inst.find_repo_root(sub) == box.repo


@pytest.mark.usefixtures("no_outer_markers")
def test_find_repo_root_passes_a_harness_directory_in_home(box: Sandbox) -> None:
    (box.home / ".claude").mkdir()
    (box.home / ".codex").mkdir()
    notes = box.home / "notes" / "deep"
    notes.mkdir(parents=True)
    assert inst.find_repo_root(notes, EXAMPLE.harnesses) == notes
    # Started at home itself, the walk has nowhere better to fall back to.
    assert inst.find_repo_root(box.home, EXAMPLE.harnesses) == box.home


@pytest.mark.usefixtures("no_outer_markers")
def test_find_repo_root_passes_home_through_a_symlink(
    box: Sandbox, home_link: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (box.home / ".claude").mkdir()
    notes = box.home / "notes"
    notes.mkdir()
    monkeypatch.setenv("HOME", str(home_link))
    assert inst.find_repo_root(home_link / "notes", EXAMPLE.harnesses) == notes


def test_find_repo_root_keeps_a_dotfiles_repository_at_home(box: Sandbox) -> None:
    (box.home / ".git").mkdir()
    (box.home / ".claude").mkdir()
    notes = box.home / "notes"
    notes.mkdir()
    assert inst.find_repo_root(notes, EXAMPLE.harnesses) == box.home


def test_find_repo_root_keeps_a_harness_directory_below_home(box: Sandbox) -> None:
    (box.home / ".claude").mkdir()
    project = box.home / "project"
    (project / ".claude").mkdir(parents=True)
    sub = project / "a"
    sub.mkdir()
    assert inst.find_repo_root(sub, EXAMPLE.harnesses) == project


@pytest.mark.usefixtures("no_home")
def test_find_repo_root_works_where_no_home_can_be_determined(box: Sandbox) -> None:
    project = box.repo / "inner"
    (project / ".claude").mkdir(parents=True)
    assert inst.find_repo_root(project, EXAMPLE.harnesses) == project


@pytest.mark.usefixtures("no_outer_markers")
def test_the_documented_repository_guard(box: Sandbox, tmp_path: Path) -> None:
    """The README's refusal: `.git` at the walk's result or above it."""

    def in_repository(start: Path) -> bool:
        root = inst.find_repo_root(start, EXAMPLE.harnesses)
        return any((d / ".git").exists() for d in (root, *root.parents))

    # A subdirectory holding its own harness config is still inside the repo.
    nested = box.repo / "inner"
    (nested / ".claude").mkdir(parents=True)
    assert inst.find_repo_root(nested, EXAMPLE.harnesses) == nested
    assert in_repository(nested)
    assert in_repository(box.repo)
    # A home directory holding a harness config is not a repository.
    (box.home / ".claude").mkdir()
    notes = box.home / "notes"
    notes.mkdir()
    assert not in_repository(notes)
    # Neither is a directory with no marker anywhere above it.
    bare = tmp_path / "nowhere"
    bare.mkdir()
    assert not in_repository(bare)


def test_codex_install_alone_resolves_the_mode(box: Sandbox) -> None:
    inst.write_artifact(SOLO, SOLO.skills[0], "local", box.repo, CODEX)
    assert inst.installed_mode(SOLO, box.repo) == "local"
    inst.write_artifact(SOLO, SOLO.skills[0], "global", box.repo, CODEX)
    assert inst.installed_mode(SOLO, box.repo) == "global"


def test_skill_stub_paths_include_mode_and_harness(box: Sandbox) -> None:
    skill = SOLO.skills[0]
    assert inst.skill_stub_paths(SOLO, box.repo) == [
        (skill, "global", CLAUDE_CODE, box.home / ".claude/skills/use-solo/SKILL.md"),
        (skill, "global", CODEX, box.home / ".agents/skills/use-solo/SKILL.md"),
        (skill, "local", CLAUDE_CODE, box.repo / ".claude/skills/use-solo/SKILL.md"),
        (skill, "local", CODEX, box.repo / ".agents/skills/use-solo/SKILL.md"),
    ]


def test_previous_skill_names_are_checked_and_cleaned_per_harness(box: Sandbox) -> None:
    inst.install(EXAMPLE, box.repo, "local")
    skill = dataclasses.replace(
        EXAMPLE.skills[0], name="fresh", previous_names=("example",)
    )
    host = dataclasses.replace(EXAMPLE, artifacts=(skill,))
    old_paths = [
        inst.previous_paths(host, skill, "local", box.repo, harness)[0][1]
        for harness in host.harnesses
    ]
    rows = [r for r in inst.check(host, box.repo) if r.status == "stale"]
    assert [(r.harness, r.path) for r in rows] == list(
        zip(host.harnesses, old_paths, strict=True)
    )
    report = inst.install(host, box.repo, "local")
    assert report.renamed == tuple(old_paths)
    assert all(not p.parent.exists() for p in old_paths)
    # Unstamped previous names are reported for each harness and never deleted.
    for path in old_paths:
        path.parent.mkdir(parents=True)
        path.write_text("mine\n")
    assert inst.leftover_previous(host, "local", box.repo) == old_paths
    assert inst.install(host, box.repo, "local").leftover == tuple(old_paths)
    assert all(p.read_text() == "mine\n" for p in old_paths)
