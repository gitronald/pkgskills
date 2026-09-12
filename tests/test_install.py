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
from pkgskills.host import Host
from pkgskills.rendering import render
from pkgskills.testing import Sandbox


def _statuses(host: Host, root: Path, mode: str | None = None) -> dict[str, str]:
    rows = inst.check(host, root, mode)  # type: ignore[arg-type]
    return {
        f"{row.artifact.kind.value}:{row.artifact.name}": row.status for row in rows
    }


def test_artifact_paths_per_mode_and_kind(box: Sandbox) -> None:
    skill, rule, agent = EXAMPLE.artifacts
    assert inst.artifact_path(EXAMPLE, skill, "global", box.repo) == (
        box.home / ".claude/skills/example/SKILL.md"
    )
    assert inst.artifact_path(EXAMPLE, skill, "local", box.repo) == (
        box.repo / ".claude/skills/example/SKILL.md"
    )
    assert inst.artifact_path(EXAMPLE, rule, "local", box.repo) == (
        box.repo / ".claude/rules/examplehost.md"
    )
    assert inst.artifact_path(EXAMPLE, agent, "local", box.repo) == (
        box.repo / ".claude/agents/example-reviewer.md"
    )


def test_find_repo_root_walks_up_and_falls_back(box: Sandbox, tmp_path: Path) -> None:
    sub = box.repo / "a" / "b"
    sub.mkdir(parents=True)
    assert inst.find_repo_root(sub) == box.repo
    bare = tmp_path / "nowhere" / "deep"
    bare.mkdir(parents=True)
    assert inst.find_repo_root(bare) == bare
    claude_only = tmp_path / "c"
    (claude_only / ".claude").mkdir(parents=True)
    assert inst.find_repo_root(claude_only / "x", EXAMPLE.harness) == claude_only


def test_check_reports_missing_before_install(box: Sandbox) -> None:
    rows = inst.check(EXAMPLE, box.repo)
    assert {row.status for row in rows} == {"missing"}
    assert all(row.mode == "global" for row in rows)


def test_install_local_writes_every_artifact_then_checks_ok(box: Sandbox) -> None:
    report = inst.install(EXAMPLE, box.repo, "local")
    assert len(report.written) == 3
    assert all(p.is_file() and box.repo in p.parents for p in report.written)
    assert _statuses(EXAMPLE, box.repo, "local") == {
        "skill:example": "ok",
        "rule:examplehost": "ok",
        "agent:example-reviewer": "ok",
    }
    # Without a mode, check judges whatever is installed, and finds the same.
    assert set(_statuses(EXAMPLE, box.repo).values()) == {"ok"}
    assert all(row.mode == "local" for row in inst.check(EXAMPLE, box.repo))


def test_install_global_lives_under_home(box: Sandbox) -> None:
    report = inst.install(SOLO, box.repo, "global")
    assert report.written == (box.home / ".claude/skills/use-solo/SKILL.md",)
    assert inst.installed_mode(SOLO, box.repo) == "global"


def test_installed_mode_prefers_global(box: Sandbox) -> None:
    assert inst.installed_mode(SOLO, box.repo) is None
    inst.install(SOLO, box.repo, "local")
    assert inst.installed_mode(SOLO, box.repo) == "local"
    inst.install(SOLO, box.repo, "global")
    assert inst.installed_mode(SOLO, box.repo) == "global"


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
    assert len(report.written) == len(MULTI.artifacts)
    assert not (box.repo / ".claude/references").exists()
    assert set(_statuses(MULTI, box.repo)) == {"skill:tidy", "skill:audit"}
    assert set(_statuses(MULTI, box.repo).values()) == {"ok"}


def test_version_only_bump_is_not_drift(box: Sandbox) -> None:
    inst.install(EXAMPLE, box.repo, "local")
    bumped = dataclasses.replace(EXAMPLE, version="1.3.0")
    assert set(_statuses(bumped, box.repo).values()) == {"ok"}


def test_moved_copy_is_judged_by_its_location(box: Sandbox) -> None:
    skill = SOLO.skills[0]
    path = inst.artifact_path(SOLO, skill, "global", box.repo)
    path.parent.mkdir(parents=True)
    path.write_text(render(SOLO, skill, "local"), encoding="utf-8")
    row = inst.check_artifact(SOLO, skill, "global", box.repo)
    assert row.status == "drifted"
    assert "mode=local" in row.reason


def test_hand_edited_body_is_drift(box: Sandbox) -> None:
    (path,) = inst.install(SOLO, box.repo, "local").written
    path.write_text(path.read_text() + "\nextra line\n", encoding="utf-8")
    row = inst.check(SOLO, box.repo)[0]
    assert row.status == "drifted"
    assert row.reason == "content differs from the current render"


def test_foreign_shapes(box: Sandbox) -> None:
    skill = SOLO.skills[0]
    path = inst.artifact_path(SOLO, skill, "local", box.repo)
    path.parent.mkdir(parents=True)

    path.write_text("---\nname: use-solo\n---\nhand written\n", encoding="utf-8")
    row = inst.check_artifact(SOLO, skill, "local", box.repo)
    assert (row.status, row.reason) == (
        "foreign",
        "no stamp; hand-written or from an older release",
    )

    path.write_text(
        "<!-- generated by otherpkg 1.0 via pkgskills 0.1 (mode=local) -->\n"
    )
    row = inst.check_artifact(SOLO, skill, "local", box.repo)
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
        row = inst.check_artifact(SOLO, skill, "local", box.repo)
        assert row.status == "foreign"
        assert row.reason == (
            "a solohost stamp pkgskills did not write; hand-edited, or from a "
            "release before solohost adopted pkgskills"
        )
        # The reason states the cause only; run_install appends the remedy.
        assert "--force" not in row.reason

    path.write_bytes(b"\xff\xfe\x00 not utf-8")
    assert inst.check_artifact(SOLO, skill, "local", box.repo).reason.startswith(
        "unreadable"
    )

    path.unlink()
    path.symlink_to(box.repo / "nowhere")
    row = inst.check_artifact(SOLO, skill, "local", box.repo)
    assert (row.status, row.reason) == ("foreign", "a symlink, not a plain file")

    path.unlink()
    path.mkdir()
    row = inst.check_artifact(SOLO, skill, "local", box.repo)
    assert (row.status, row.reason) == ("foreign", "a directory, not a file")


def test_prose_mention_of_the_marker_is_not_a_stamp(box: Sandbox) -> None:
    skill = SOLO.skills[0]
    path = inst.artifact_path(SOLO, skill, "local", box.repo)
    path.parent.mkdir(parents=True)
    path.write_text(
        "Files say <!-- generated by solohost 1 via pkgskills 1 (mode=local) --> "
        "when generated.\n"
    )
    assert not inst.is_generated(path, SOLO)


def test_reinstall_over_own_copy_needs_no_force(box: Sandbox) -> None:
    inst.install(SOLO, box.repo, "local")
    inst.install(SOLO, box.repo, "local")
    assert _statuses(SOLO, box.repo) == {"skill:use-solo": "ok"}


def test_foreign_target_is_refused_before_anything_is_written(box: Sandbox) -> None:
    rule_path = inst.artifact_path(EXAMPLE, EXAMPLE.rules[0], "local", box.repo)
    rule_path.parent.mkdir(parents=True)
    rule_path.write_text("my own rule\n")
    with pytest.raises(inst.ForeignArtifactError) as excinfo:
        inst.install(EXAMPLE, box.repo, "local")
    assert excinfo.value.path == rule_path
    assert "no stamp" in excinfo.value.reason
    assert not inst.artifact_path(
        EXAMPLE, EXAMPLE.skills[0], "local", box.repo
    ).exists()
    assert rule_path.read_text() == "my own rule\n"


def test_force_replaces_a_symlink_without_writing_through(box: Sandbox) -> None:
    target = box.repo / "elsewhere.md"
    target.write_text("untouched\n")
    path = inst.artifact_path(SOLO, SOLO.skills[0], "local", box.repo)
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
    rule_local = inst.artifact_path(EXAMPLE, EXAMPLE.rules[0], "local", box.repo)
    rule_local.write_text("hand edited, but keeps no stamp\n")
    report = inst.install(EXAMPLE, box.repo, "global")
    removed = set(report.removed)
    assert inst.artifact_path(EXAMPLE, EXAMPLE.skills[0], "local", box.repo) in removed
    assert inst.artifact_path(EXAMPLE, EXAMPLE.agents[0], "local", box.repo) in removed
    assert rule_local not in removed and rule_local.exists()


def test_local_install_reports_a_shadowing_global_copy(box: Sandbox) -> None:
    inst.install(SOLO, box.repo, "global")
    report = inst.install(SOLO, box.repo, "local")
    assert report.shadowed == (
        inst.artifact_path(SOLO, SOLO.skills[0], "local", box.repo),
    )
    assert inst.shadowed_skills(SOLO, box.repo) == list(report.shadowed)


def test_check_without_mode_reports_both_locations(box: Sandbox) -> None:
    inst.install(SOLO, box.repo, "global")
    inst.install(SOLO, box.repo, "local")
    rows = inst.check(SOLO, box.repo)
    assert [row.mode for row in rows] == ["global", "local"]
    assert all(row.ok for row in rows)


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
        local = inst.artifact_path(EXAMPLE, art, "local", box.repo)
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
    local = inst.artifact_path(EXAMPLE, rule, "local", box.repo)
    local.parent.mkdir(parents=True, exist_ok=True)
    local.write_text(
        render(EXAMPLE, rule, "local") + "\nhand-edited\n", encoding="utf-8"
    )

    row = inst.check_artifact(EXAMPLE, rule, "local", box.repo)
    assert row.status == "stale"
    assert "remove it" in row.reason


def test_a_foreign_local_file_is_never_called_stale(box: Sandbox) -> None:
    inst.install(EXAMPLE, box.repo, "global")
    rule = EXAMPLE.rules[0]
    local = inst.artifact_path(EXAMPLE, rule, "local", box.repo)
    local.parent.mkdir(parents=True, exist_ok=True)
    local.write_text("someone else's file\n", encoding="utf-8")
    assert inst.check_artifact(EXAMPLE, rule, "local", box.repo).status == "foreign"


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
    # Nothing is on disk, so the honest answer is False; the caller's handed-in
    # verdict is what decides, and "auto" re-derives it.
    assert inst.stale_local(EXAMPLE, rule, "local", box.repo, installed="global")
    assert not inst.stale_local(EXAMPLE, rule, "local", box.repo, installed=None)
    assert not inst.stale_local(EXAMPLE, rule, "local", box.repo)


def test_local_only_copies_are_not_stale(box: Sandbox) -> None:
    inst.install(EXAMPLE, box.repo, "local")
    assert set(_statuses(EXAMPLE, box.repo).values()) == {"ok"}
    assert not inst.stale_local(EXAMPLE, EXAMPLE.rules[0], "local", box.repo)


def test_stale_needs_a_resolved_global_install_not_a_default(box: Sandbox) -> None:
    # Nothing installed anywhere: `installed_mode` is None, not "global".
    assert inst.installed_mode(EXAMPLE, box.repo) is None
    assert not inst.stale_local(EXAMPLE, EXAMPLE.rules[0], "local", box.repo)


def test_no_stale_verdict_when_repo_root_is_home(box: Sandbox) -> None:
    os.chdir(box.home)
    (box.home / ".git").mkdir()
    inst.install(EXAMPLE, box.home, "global")
    # The two paths coincide, so there is one file, not a leftover second one.
    for art in EXAMPLE.artifacts:
        assert not inst.stale_local(EXAMPLE, art, "local", box.home)


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
    stray = inst.artifact_path(MULTI, skill, "global", box.repo)
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
    assert not inst.stale_local(local_only, rule, "local", box.repo)
    # Even handed a global verdict outright: there is no global install of this
    # host for a per-repo copy to be leftovers from.
    assert not inst.stale_local(local_only, rule, "local", box.repo, installed="global")
    assert inst.stale_local(EXAMPLE, rule, "local", box.repo, installed="global")


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
    inst.install(SOLO, box.home, "local")
    report = inst.install(SOLO, box.home, "global")
    assert report.removed == ()
    assert inst.artifact_path(SOLO, SOLO.skills[0], "global", box.home).exists()
