"""Split and parse the fenced frontmatter that prompt files open with.

Skills, rules, and agents all start with an optional ``---`` fenced block of
flat ``key: value`` pairs. The harness reads ``name`` and ``description`` off
the installed file to decide when a skill fires, so a generated stub has to
carry that block byte for byte; the body behind it is what the host prints on
demand. ``split_frontmatter`` is therefore lossless: ``raw + body`` rebuilds the
input exactly whenever a block was found.

YAML parses scalar values, comments, and quoting. The flat view exposes only
scalar values; nested mappings and sequences remain available in ``raw`` for
the specification checker.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import yaml

FENCE = "---"


@dataclass(frozen=True)
class Frontmatter:
    """A parsed frontmatter block.

    ``raw`` is the block as it appeared, both fence lines included and ending in
    the source's original line endings, so it can be re-emitted verbatim.
    ``fields`` holds the flat
    scalar keys the block declares.
    """

    raw: str
    fields: dict[str, str] = field(default_factory=dict)

    def get(self, key: str, default: str | None = None) -> str | None:
        """The value of ``key``, or ``default`` when the block lacks it."""
        return self.fields.get(key, default)


def split_frontmatter(text: str) -> tuple[Frontmatter | None, str]:
    """Split ``text`` into ``(frontmatter, body)``.

    Returns ``(None, text)`` when there is no opening fence on the first line
    or the block is never closed, so the body is always the input verbatim in
    that case. Never raises.
    """
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].rstrip("\r\n") != FENCE:
        return None, text
    for i in range(1, len(lines)):
        if lines[i].rstrip("\r\n") == FENCE:
            raw = "".join(lines[: i + 1])
            body = "".join(lines[i + 1 :])
            return Frontmatter(raw=raw, fields=parse_fields(lines[1:i])), body
    return None, text


def parse_fields(lines: list[str]) -> dict[str, str]:
    """A flat string view of YAML, with an empty value for nested collections.

    BaseLoader decodes scalars without resolving numbers or booleans; type
    validation belongs to the spec checker. Invalid YAML yields no fields so
    splitting remains lossless and never raises.
    """
    try:
        parsed = yaml.load("".join(lines), Loader=yaml.BaseLoader)
    except yaml.YAMLError:
        return {}
    if not isinstance(parsed, dict):
        return {}
    return {
        key: value if isinstance(value, str) else "" for key, value in parsed.items()
    }


def body_only(text: str) -> str:
    """``text`` with any leading frontmatter removed."""
    _, body = split_frontmatter(text)
    return body
