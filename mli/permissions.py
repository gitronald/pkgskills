"""Automation-level permission profiles for a host's shell-outs.

A host whose skills tell the model to run commands has a prompt-fatigue problem:
whether each command runs unprompted depends on the ambient Claude Code
permission config, which the skill prompts never declare. Nothing about the
solution is host-specific except the rule list, so the ladder, the merge, and the
file layout live here and the host declares only its own per-level increments as
:attr:`Host.permissions <mli.host.Host.permissions>`.

Levels form an escalating, superset ladder named by supervision posture rather
than by any one host's commands:

* ``none``    — grant nothing; every command falls to the session mode and the
                classifier (fully portable, most prompts).
* ``assist``  — everything local and reversible.
* ``confirm`` — ``assist`` plus the publishing step, so a run pauses only at the
                irreversible one.
* ``full``    — ``confirm`` plus the irreversible step: nothing is confirmed.

What fills each rung is the host's call; the postures are what stay comparable
across tools. The rule sets are computed here (pure) and the CLI reads and writes
``settings.json``. Grants are applied *additively* and never downgrade an existing
``deny``/``ask`` rule — a deliberate stricter policy always wins.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from mli.host import Host, Mode

__all__ = [
    "LEVELS",
    "SETTINGS_GLOBAL_REL",
    "SETTINGS_LOCAL_REL",
    "Level",
    "MergeResult",
    "invocation_rule",
    "levels",
    "merge_allow",
    "parse_level",
    "render_block",
    "rules_for",
    "settings_path",
]


class Level(StrEnum):
    """An automation level: how far a host's commands run without a prompt."""

    none = "none"
    assist = "assist"
    confirm = "confirm"
    full = "full"


# Lowest to highest. Each level is a superset of the ones before it.
LEVELS: tuple[Level, ...] = (Level.none, Level.assist, Level.confirm, Level.full)

# The personal, git-ignored per-repo settings file (local mode) vs. the user-wide
# one (global mode). Local scopes a broad grant to one checkout and is never
# committed for collaborators.
SETTINGS_GLOBAL_REL = Path(".claude/settings.json")
SETTINGS_LOCAL_REL = Path(".claude/settings.local.json")


def levels() -> list[str]:
    """The automation-level names, lowest to highest."""
    return [level.value for level in LEVELS]


def parse_level(name: str) -> Level:
    """Resolve a level name — or its ``0``-``3`` numeric alias — to a :class:`Level`.

    ``"0"``-``"3"`` map to the ladder by position; every other value raises
    ``ValueError`` so the caller can report the valid choices.
    """
    if name.isdigit():
        index = int(name)
        if 0 <= index < len(LEVELS):
            return LEVELS[index]
        raise ValueError(name)
    return Level(name)


def invocation_rule(host: Host, mode: Mode) -> str:
    """The allow-rule that lets the model call ``host``'s own CLI.

    Derived from :meth:`Host.invocation <mli.host.Host.invocation>`, so it is
    mode-aware for the same reason everything else here is: a global install is
    invoked as bare ``<cli>`` and needs its own grant, while a local install runs
    ``uv run <cli>`` and is already covered by the broader ``Bash(uv run:*)``
    that a host's own increments carry. Deduplication in :func:`rules_for` makes
    the overlap a no-op either way.
    """
    prefix = host.cli if mode == "global" else host.local_prefix
    return f"Bash({prefix}:*)"


def _lowest_granting(increments: Mapping[Level, Sequence[str]]) -> Level | None:
    """The lowest level at which ``increments`` grants anything, if any."""
    for level in LEVELS:
        if increments.get(level):
            return level
    return None


def rules_for(host: Host, level: Level, mode: Mode = "global") -> list[str]:
    """The allow-rules pre-authorizing everything up to and including ``level``.

    Cumulative: the union of every increment from ``none`` through ``level``,
    plus the CLI's own invocation rule, which joins at the lowest level the host
    grants anything at — a host that grants nothing needs no way to be called
    unattended either. Deduplicated, in ascending-level order, for reproducible
    output.
    """
    increments = host.permissions
    joins_at = _lowest_granting(increments)
    out: list[str] = []
    seen: set[str] = set()
    for lvl in LEVELS:
        chunk = list(increments.get(lvl, ()))
        if lvl is joins_at:
            chunk.append(invocation_rule(host, mode))
        for rule in chunk:
            if rule not in seen:
                seen.add(rule)
                out.append(rule)
        if lvl is level:
            break
    return out


def settings_path(root: Path, mode: Mode) -> Path:
    """Where a profile is written for ``mode``.

    Global targets ``~/.claude/settings.json`` (applies to every repo); local
    targets the repo's ``.claude/settings.local.json`` — the personal,
    git-ignored file — so a broad grant stays scoped to one checkout.
    """
    if mode == "global":
        return Path.home() / SETTINGS_GLOBAL_REL
    return root / SETTINGS_LOCAL_REL


@dataclass(frozen=True)
class MergeResult:
    """The outcome of merging rules into a permissions block.

    ``permissions`` is a fresh block (the input is never mutated); ``added`` were
    appended to ``allow``, ``already`` were present on ``allow`` (no-ops), and
    ``skipped`` are ``(rule, reason)`` pairs left untouched because an existing
    ``deny``/``ask`` rule already governs them.
    """

    permissions: dict[str, Any]
    added: list[str]
    already: list[str]
    skipped: list[tuple[str, str]]


def _string_list(value: Any) -> list[str]:
    """The string members of ``value`` when it is a list, else an empty list."""
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str)]
    return []


def merge_allow(permissions: dict[str, Any], rules: Sequence[str]) -> MergeResult:
    """Additively merge ``rules`` into ``permissions['allow']``, deferring to policy.

    Never removes or weakens an existing rule: a rule whose exact string is
    already on ``deny`` or ``ask`` is left there and reported as skipped (a
    deliberate stricter policy wins), a rule already on ``allow`` is a no-op, and
    everything else is appended to ``allow``. Matching is by exact rule string —
    subsuming a broader pattern is the harness matcher's job, not this merge's.
    Returns a new permissions block plus a report; the input is not mutated.
    """
    allow = _string_list(permissions.get("allow"))
    deny = set(_string_list(permissions.get("deny")))
    ask = set(_string_list(permissions.get("ask")))
    present = set(allow)

    new_allow = list(allow)
    added: list[str] = []
    already: list[str] = []
    skipped: list[tuple[str, str]] = []
    for rule in rules:
        if rule in deny:
            skipped.append((rule, "already on deny"))
        elif rule in ask:
            skipped.append((rule, "already on ask"))
        elif rule in present:
            already.append(rule)
        else:
            new_allow.append(rule)
            present.add(rule)
            added.append(rule)

    new_permissions = dict(permissions)
    new_permissions["allow"] = new_allow
    return MergeResult(
        permissions=new_permissions, added=added, already=already, skipped=skipped
    )


def render_block(rules: Sequence[str]) -> str:
    """A paste-ready ``settings.json`` fragment granting ``rules`` on ``allow``."""
    return json.dumps({"permissions": {"allow": list(rules)}}, indent=2) + "\n"
