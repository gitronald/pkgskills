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


def strip_comment(value: str) -> str:
    """``value`` with a trailing YAML comment removed.

    YAML opens a comment at a ``#`` that starts the token or follows
    whitespace, and never inside a quoted scalar. Anything else belongs to the
    value: ``a#b`` is the string ``a#b``. Stripping matters because the callers
    ask what YAML would *resolve* a scalar to — ``1.0  # bump me`` is the float
    ``1.0``, and comparing the whole line against a number would miss it.
    """
    quote = ""
    for i, ch in enumerate(value):
        if quote:
            if ch == quote:
                quote = ""
        elif ch in "\"'":
            quote = ch
        elif ch == "#" and (i == 0 or value[i - 1] in " \t"):
            return value[:i].rstrip()
    return value


@dataclass(frozen=True)
class Block:
    """An indented block under one top-level frontmatter key.

    :func:`parse_fields` flattens a nested mapping to an empty string, because
    no prompt kind needs to *read* one. Two callers need to inspect one anyway
    — ``mli`` splices its own version keys into ``metadata``, and the spec
    check asks whether that mapping is the string-to-string map the
    specification requires — so the raw lines are offered here rather than
    walked separately in each place.

    ``at`` indexes the ``key:`` line within ``raw.splitlines()``. ``inline`` is
    whatever followed the colon on that line with any comment stripped, so it
    is empty both for a bare ``key:`` and for one carrying only a note.
    ``lines`` are the continuation lines verbatim, blanks included.
    """

    at: int
    inline: str
    lines: list[str] = field(default_factory=list)

    def entries(self) -> list[tuple[int, str, str]]:
        """``(indent, key, value)`` per continuation line that declares one.

        Blank lines and comments are dropped; a line that is not ``key: value``
        yields an empty key, so a caller can report it rather than skip it. A
        sequence item is one of those even when it carries a colon of its own:
        ``- key: value`` opens a list, not a mapping, and reading it as a pair
        would let a block that is the wrong shape entirely pass for the right
        one.
        """
        out: list[tuple[int, str, str]] = []
        for line in self.lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            indent = len(line) - len(line.lstrip())
            key, sep, value = stripped.partition(":")
            # With no colon — or with a leading `-` — there is no key, and the
            # whole line is what a caller needs to quote back. Reporting it as
            # an empty pair would name nothing.
            if not sep or stripped.startswith("-"):
                out.append((indent, "", stripped))
            else:
                out.append((indent, key.strip(), strip_comment(value.strip())))
        return out


def find_block(raw: str, key: str) -> Block | None:
    """The block ``key`` opens in a raw frontmatter block, or ``None``.

    The continuation runs to the first line that is neither indented nor
    blank — the closing fence included. Blank lines are kept inside it, so a
    mapping split by one is not silently truncated at the gap.

    A key declared twice resolves to the **last** occurrence, which is what
    YAML does and what :func:`parse_fields` already records. Returning the
    first would let a caller check one block while the harness loads another.
    """
    lines = raw.splitlines()
    close = len(lines) - 1
    found: Block | None = None
    for i in range(1, close):
        name, sep, value = lines[i].partition(":")
        if not sep or name.strip() != key or name[:1].isspace():
            continue
        run: list[str] = []
        for line in lines[i + 1 : close]:
            if line.strip() and not line[:1].isspace():
                break
            run.append(line)
        while run and not run[-1].strip():
            run.pop()
        found = Block(at=i, inline=strip_comment(value.strip()), lines=run)
    return found


def body_only(text: str) -> str:
    """``text`` with any leading frontmatter removed."""
    _, body = split_frontmatter(text)
    return body
