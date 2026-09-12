"""Pure transforms from a host declaration to the bytes that get installed.

Nothing here touches the filesystem beyond reading package data. The text a
renderer returns is exactly what ``install`` writes and exactly what
``install --check`` compares against, so the two can never disagree.
"""

from __future__ import annotations

import json

from pkgskills.frontmatter import split_frontmatter
from pkgskills.host import CLI_TOKEN, Agent, Artifact, Doc, Host, Mode, Rule, Skill
from pkgskills.spec import SPEC, SpecError
from pkgskills.stamp import place_stamp, render_stamp


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
    inv = host.invocation(mode) if host.renders_cli(skill) else None
    return render_prompt(host.read(source), inv)


def doc_body(host: Host, doc: Doc, mode: Mode) -> str:
    """The printable text of a reference document.

    The same render a skill body gets, deliberately: a doc is a body that
    happens to be loaded by a step rather than by a trigger, so ``{cli}`` has
    to come out the same way in both.
    """
    inv = host.invocation(mode) if host.renders_cli(doc) else None
    return render_prompt(host.read(doc.source), inv)


def _single_line(text: str) -> str:
    return " ".join(text.split())


def stub_frontmatter(host: Host, skill: Skill) -> str:
    """The stub's frontmatter block, fences included.

    A single-source skill lifts its source's block verbatim, so the trigger
    text -- and any ``metadata`` the source declares, its own ``version``
    included -- has one home. A dispatcher generates its own block from
    ``description`` or from the subcommand list; it has no source to carry a
    version, so it declares no ``metadata`` at all.
    """
    if not skill.dispatches:
        source = skill.sources[0]
        front, _ = split_frontmatter(host.read(source))
        # The stub *is* the skill the harness loads, so a source that breaks
        # the spec would install a broken skill. Report every way it does,
        # rather than the first one this function happens to trip over.
        header = f"skill {skill.name!r} cannot be rendered into a stub"
        violations = SPEC.check_parsed(source, front)
        if front is None:
            raise SpecError(violations, header=header)
        violations.extend(SPEC.check_skill_name(source, front, skill))
        if violations:
            raise SpecError(violations, header=header)
        return front.raw
    description = (
        skill.description
        if skill.description is not None
        else (
            f"`{host.dist}` toolkit. Invoke as `/{skill.name} <subcommand> [args]`. "
            f"Subcommands: {', '.join(skill.subcommands)}."
        )
    )
    raw = (
        f"---\nname: {json.dumps(skill.name)}\n"
        f"description: {json.dumps(_single_line(description))}\n---\n"
    )
    violations = SPEC.check_frontmatter(f"{skill.name}/{SPEC.entry_file}", raw)
    if violations:
        raise SpecError(violations, header=f"skill {skill.name!r} cannot be rendered")
    return raw


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
            f"- `{sub}`" + (f" - {description}" if description else "")
            for sub, source in zip(skill.subcommands, skill.sources, strict=True)
            for description in [_subcommand_description(host, source)]
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
{host.skill_command(mode, skill.body_names[0])}
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
    if host.renders_cli(art):
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
