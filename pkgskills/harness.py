"""Where a harness reads each artifact kind from disk.

A harness is the tool that loads prompts off the filesystem: today that is
Claude Code, which reads skills from ``.claude/skills/<name>/SKILL.md``, rules
from ``.claude/rules/<name>.md``, and subagents from ``.claude/agents/<name>.md``,
each under either the user's home directory (global) or a repository root
(local). The relative layout is identical at both bases, so a global install
and a local install never collide on one file.

Keeping the layout in one object is what lets a second harness land once for
every host: a new :class:`Harness` value, no host changes.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType


class Kind(StrEnum):
    """The artifact kinds a harness reads from disk."""

    SKILL = "skill"
    RULE = "rule"
    AGENT = "agent"


@dataclass(frozen=True)
class Harness:
    """A harness's on-disk layout for generated artifacts.

    ``layout`` maps each kind to a path template relative to the mode base
    (``$HOME`` or the repo root) with a ``{name}`` placeholder. ``config_dir``
    is the directory whose presence marks a repository root for that harness,
    used alongside ``.git`` when walking up from a working directory.

    ``shadowed_kinds`` names the kinds whose global copy *hides* the local one.
    Every other kind loads from both bases at once, which is what makes a
    leftover per-repo copy a live extra file rather than an inert one. It is a
    property of the harness, not of any host, so it is declared here.
    """

    name: str
    config_dir: str
    layout: Mapping[Kind, str] = field(default_factory=dict)
    shadowed_kinds: frozenset[Kind] = frozenset()

    def shadows(self, kind: Kind) -> bool:
        """True when a global artifact of ``kind`` hides the local copy."""
        return kind in self.shadowed_kinds

    def both_load(self, kind: Kind) -> bool:
        """True when global and local copies of ``kind`` are loaded together."""
        return kind not in self.shadowed_kinds

    def relative_path(self, kind: Kind, name: str) -> Path:
        """The artifact's path for ``kind`` and ``name``, relative to its base."""
        try:
            template = self.layout[kind]
        except KeyError:
            raise ValueError(
                f"harness {self.name!r} has no location for {kind.value} artifacts"
            ) from None
        return Path(template.format(name=name))

    def supports(self, kind: Kind) -> bool:
        """True when the harness has a location for ``kind``."""
        return kind in self.layout


CLAUDE_CODE = Harness(
    name="claude-code",
    config_dir=".claude",
    layout=MappingProxyType(
        {
            Kind.SKILL: ".claude/skills/{name}/SKILL.md",
            Kind.RULE: ".claude/rules/{name}.md",
            Kind.AGENT: ".claude/agents/{name}.md",
        }
    ),
    # Claude Code resolves a skill by name with the global one winning, but
    # auto-loads rules and agents from both bases at once.
    shadowed_kinds=frozenset({Kind.SKILL}),
)
