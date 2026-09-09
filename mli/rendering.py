"""Pure transforms from a host declaration to the bytes that get installed.

Nothing here touches the filesystem beyond reading package data. The text a
renderer returns is exactly what ``install`` writes and exactly what
``install --check`` compares against, so the two can never disagree.
"""

from __future__ import annotations

from mli.frontmatter import split_frontmatter
from mli.host import CLI_TOKEN, Agent, Artifact, Host, Mode, Rule, Skill
from mli.stamp import METADATA_KEYS, metadata_lines, place_stamp, render_stamp


def render_prompt(text: str, invocation: str | None = None) -> str:
    """A prompt body ready to print: frontmatter stripped, ``{cli}`` rendered.

    ``invocation`` is the mode-correct prefix to substitute; ``None`` leaves
    the placeholder untouched for bodies that never opted in. Surrounding
    whitespace is trimmed and a single trailing newline ensured.
    """
    _, body = split_frontmatter(text)
    if invocation is not None:
        body = body.replace(CLI_TOKEN, invocation)
    return body.strip() + "\n"


def skill_body(host: Host, skill: Skill, source: str, mode: Mode) -> str:
    """The printable body of one skill source."""
    inv = host.invocation(mode) if skill.render_cli else None
    return render_prompt(host.read(source), inv)


def _single_line(text: str) -> str:
    return " ".join(text.split())


def with_metadata(raw: str, host: Host, skill: Skill) -> str:
    """``raw`` frontmatter with mli's version keys under ``metadata``.

    The keys join an existing ``metadata`` mapping when the source declares
    one, and open a new one just before the closing fence otherwise. Every
    other line is left byte for byte, since the harness reads this block.
    A source that already declares one of mli's keys is rejected rather than
    emitted as a duplicate key.
    """
    lines = raw.splitlines()
    close = len(lines) - 1
    at = next(
        (i for i in range(1, close) if lines[i].rstrip() == "metadata:"),
        None,
    )
    if at is None:
        block = ["metadata:", *metadata_lines(host)]
        return "\n".join([*lines[:close], *block, lines[close], ""])
    for line in lines[at + 1 : close]:
        if line[:1] not in (" ", "\t"):
            break
        key = line.split(":", 1)[0].strip()
        if key in METADATA_KEYS:
            raise ValueError(
                f"skill {skill.name!r}: source frontmatter already declares "
                f"metadata.{key}; mli writes that key, so drop it from the source"
            )
    return "\n".join([*lines[: at + 1], *metadata_lines(host), *lines[at + 1 :], ""])


def stub_frontmatter(host: Host, skill: Skill) -> str:
    """The stub's frontmatter block, fences included.

    A single-source skill lifts its source's block so the trigger text has one
    home. A dispatcher generates its own, from ``description`` or from the
    subcommand list. Either way the block gains the ``metadata`` versions.
    """
    if not skill.dispatches:
        front, _ = split_frontmatter(host.read(skill.sources[0]))
        if front is None:
            raise ValueError(
                f"skill {skill.name!r}: source {skill.sources[0]!r} has no "
                "frontmatter; a stub needs its name and description"
            )
        declared = front.get("name")
        if declared != skill.name:
            raise ValueError(
                f"skill {skill.name!r}: source frontmatter names {declared!r}; "
                "the two must agree"
            )
        if not front.get("description"):
            raise ValueError(f"skill {skill.name!r}: source has no description")
        return with_metadata(front.raw, host, skill)
    description = skill.description or (
        f"`{host.dist}` toolkit. Invoke as `/{skill.name} <subcommand> [args]`. "
        f"Subcommands: {', '.join(skill.subcommands)}."
    )
    generated = (
        f"---\nname: {skill.name}\ndescription: {_single_line(description)}\n---\n"
    )
    return with_metadata(generated, host, skill)


def _subcommand_description(host: Host, source: str) -> str:
    front, _ = split_frontmatter(host.read(source))
    return _single_line(front.get("description") or "") if front else ""


def render_stub(host: Host, skill: Skill, mode: Mode) -> str:
    """The generated ``SKILL.md`` stub for ``skill`` in ``mode``."""
    inv = host.invocation(mode)
    check = host.check_command(mode)
    repair = host.install_command(mode, force=True)
    head = f"""\
# {skill.name}

This file is a generated stub, not the source of truth. The instructions live
in the `{host.dist}` package and are printed on demand, so they always match
the installed version.

**Before following them, confirm this stub is current:**

```bash
{check}
```

Anything other than `ok` means this stub predates the installed package: run
`{repair}`, then start a fresh context before continuing.
"""
    if skill.dispatches:
        subs = "\n".join(
            f"- `{sub}` - {_subcommand_description(host, source)}".rstrip(" -")
            for sub, source in zip(skill.subcommands, skill.sources, strict=True)
        )
        slash = ", ".join(f"`/{skill.name} {sub}`" for sub in skill.subcommands)
        tail = f"""
**Pick a subcommand, load its instructions, and follow them exactly:**

```bash
{inv} skill <subcommand>
```

Subcommands ({len(skill.subcommands)}):

{subs}

These map to {slash}. If the subcommand is missing or unrecognized, run
`{inv} skill --list` and ask the user which one they want.
"""
    else:
        tail = f"""
**Load the instructions and follow them exactly:**

```bash
{host.skill_command(mode)}
```

If that command is not found, `{host.dist}` is not installed in this
environment; install it first.
"""
    return place_stamp(
        stub_frontmatter(host, skill), render_stamp(host, mode), head + tail
    )


def render_copy(
    host: Host, art: Rule | Agent, mode: Mode, *, stamp: bool = True
) -> str:
    """The installed text of a rule or agent: the source, stamped after any frontmatter.

    With ``stamp`` off, the same text minus the stamp line, for printing.
    """
    text = host.read(art.source)
    front, body = split_frontmatter(text)
    if art.render_cli:
        body = body.replace(CLI_TOKEN, host.invocation(mode))
    raw = front.raw if front else ""
    body = body.strip() + "\n"
    if not stamp:
        return f"{raw}\n{body}" if raw else body
    return place_stamp(raw, render_stamp(host, mode), body)


def render(host: Host, art: Artifact, mode: Mode) -> str:
    """The bytes ``install`` writes for ``art`` in ``mode``."""
    if isinstance(art, Skill):
        return render_stub(host, art, mode)
    return render_copy(host, art, mode)
