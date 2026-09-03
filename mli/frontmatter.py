"""Split and parse the fenced frontmatter that prompt files open with.

Skills, rules, and agents all start with an optional ``---`` fenced block of
flat ``key: value`` pairs. The harness reads ``name`` and ``description`` off
the installed file to decide when a skill fires, so a generated stub has to
carry that block byte for byte; the body behind it is what the host prints on
demand. ``split_frontmatter`` is therefore lossless: ``raw + body`` rebuilds the
input exactly whenever a block was found.

The parser is deliberately small. It handles single-line scalars, quoted
scalars, and the folded (``>``) and literal (``|``) block scalars that long
descriptions use. Nested mappings are not needed by any prompt kind and are
ignored rather than parsed.
"""

from __future__ import annotations

from dataclasses import dataclass, field

FENCE = "---"


@dataclass(frozen=True)
class Frontmatter:
    """A parsed frontmatter block.

    ``raw`` is the block as it appeared, both fence lines included and ending in
    a newline, so it can be re-emitted verbatim. ``fields`` holds the flat
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
            if not raw.endswith("\n"):
                raw += "\n"
            body = "".join(lines[i + 1 :])
            return Frontmatter(raw=raw, fields=parse_fields(lines[1:i])), body
    return None, text


def parse_fields(lines: list[str]) -> dict[str, str]:
    """Parse flat ``key: value`` lines into a dict.

    A value of ``>`` or ``|`` (optionally suffixed with ``-``) starts a block
    scalar whose indented continuation lines are joined with spaces (folded)
    or newlines (literal). Surrounding quotes on a single-line value are
    stripped. Indented lines that follow an ordinary scalar are skipped, which
    is how a nested mapping is ignored.
    """
    out: dict[str, str] = {}
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i].rstrip("\r\n")
        i += 1
        if not line.strip() or line.startswith("#") or line[0].isspace():
            continue
        key, sep, value = line.partition(":")
        if not sep:
            continue
        key = key.strip()
        value = value.strip()
        if value in (">", ">-", "|", "|-"):
            block: list[str] = []
            while i < n and (lines[i].startswith((" ", "\t")) or not lines[i].strip()):
                block.append(lines[i].strip())
                i += 1
            while block and not block[-1]:
                block.pop()
            joiner = " " if value.startswith(">") else "\n"
            out[key] = joiner.join(part for part in block if part or joiner == "\n")
            continue
        if len(value) >= 2 and value[0] in "\"'" and value[-1] == value[0]:
            value = value[1:-1]
        out[key] = value
    return out


def body_only(text: str) -> str:
    """``text`` with any leading frontmatter removed."""
    _, body = split_frontmatter(text)
    return body
