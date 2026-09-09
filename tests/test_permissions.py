"""Tests for the automation-level permission profiles."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest
from solohost.cli import HOST as SOLO

from mli import permissions as perms
from mli.host import Host
from mli.permissions import Level
from mli.testing import Sandbox

INCREMENTS = {
    Level.assist: ("Bash(git add:*)", "Bash(git commit:*)", "Bash(uv run:*)"),
    Level.confirm: ("Bash(git push:*)",),
    Level.full: ("Bash(gh pr merge:*)",),
}
HOST = dataclasses.replace(SOLO, permissions=INCREMENTS)


def test_levels_and_their_numeric_aliases() -> None:
    assert perms.levels() == ["none", "assist", "confirm", "full"]
    assert [perms.parse_level(str(i)) for i in range(4)] == list(perms.LEVELS)
    assert perms.parse_level("confirm") is Level.confirm
    with pytest.raises(ValueError):
        perms.parse_level("4")
    with pytest.raises(ValueError):
        perms.parse_level("paranoid")


def test_rules_are_cumulative_and_in_ascending_level_order() -> None:
    assert perms.rules_for(HOST, Level.none) == []
    assist = perms.rules_for(HOST, Level.assist)
    confirm = perms.rules_for(HOST, Level.confirm)
    full = perms.rules_for(HOST, Level.full)
    assert confirm == [*assist, "Bash(git push:*)"]
    assert full == [*confirm, "Bash(gh pr merge:*)"]


def test_the_invocation_rule_is_mode_aware_and_deduplicated() -> None:
    # Global: the CLI is called bare, so it needs its own grant.
    assert "Bash(solohost:*)" in perms.rules_for(HOST, Level.assist, "global")
    # Local: `uv run solohost` is already covered by the host's own uv grant,
    # so the derived rule collapses into it rather than appearing twice.
    local = perms.rules_for(HOST, Level.assist, "local")
    assert local.count("Bash(uv run:*)") == 1
    assert "Bash(solohost:*)" not in local
    # It joins at the lowest level that grants anything, not before it.
    assert perms.invocation_rule(HOST, "global") not in perms.rules_for(
        HOST, Level.none, "global"
    )


def test_a_host_that_grants_nothing_gets_no_invocation_rule() -> None:
    assert perms.rules_for(SOLO, Level.full, "global") == []


def test_none_may_not_carry_rules() -> None:
    with pytest.raises(ValueError, match="must grant nothing"):
        dataclasses.replace(SOLO, permissions={Level.none: ("Bash(rm:*)",)})
    with pytest.raises(ValueError, match="unknown permission level"):
        Host(
            dist="d",
            cli="c",
            prompts="p",
            permissions={"reckless": ("Bash(rm:*)",)},  # type: ignore[dict-item]
        )


def test_settings_path_per_mode(box: Sandbox) -> None:
    assert perms.settings_path(box.repo, "local") == (
        box.repo / ".claude/settings.local.json"
    )
    assert perms.settings_path(box.repo, "global") == (
        box.home / ".claude/settings.json"
    )


def test_merge_is_additive_and_never_downgrades() -> None:
    block = {
        "allow": ["Bash(git add:*)"],
        "deny": ["Bash(gh pr merge:*)"],
        "ask": ["Bash(git push:*)"],
    }
    result = perms.merge_allow(block, perms.rules_for(HOST, Level.full, "global"))
    assert result.added == [
        "Bash(git commit:*)",
        "Bash(uv run:*)",
        "Bash(solohost:*)",
    ]
    assert result.already == ["Bash(git add:*)"]
    assert result.skipped == [
        ("Bash(git push:*)", "already on ask"),
        ("Bash(gh pr merge:*)", "already on deny"),
    ]
    # The stricter entries stay exactly where they were, and the input is intact.
    assert result.permissions["deny"] == ["Bash(gh pr merge:*)"]
    assert result.permissions["ask"] == ["Bash(git push:*)"]
    assert block["allow"] == ["Bash(git add:*)"]


def test_merge_tolerates_a_junk_shaped_block() -> None:
    result = perms.merge_allow({"allow": "not a list", "deny": [7]}, ["Bash(x:*)"])
    assert result.added == ["Bash(x:*)"]
    assert result.permissions["allow"] == ["Bash(x:*)"]


def test_render_block_is_paste_ready() -> None:
    text = perms.render_block(["Bash(git add:*)"])
    assert json.loads(text) == {"permissions": {"allow": ["Bash(git add:*)"]}}
    assert text.endswith("\n")


def test_settings_path_is_not_created_by_computing_it(tmp_path: Path) -> None:
    assert not perms.settings_path(tmp_path, "local").exists()
