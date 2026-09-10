"""A throwaway host with two single-source skills and no dispatcher.

The shape the other two fixtures leave untested: several skills, each with one
body and one trigger. `audit` deliberately lives in a file whose stem is not
its skill name, so keying bodies by stem would break it while `tidy` kept
working. It is also the local-only host: its skills only mean anything inside
one repository, so it declares `modes=("local",)` and global mode is
unreachable for it.

It ships the reference documents too. Every body it has uses `{cli}`, so it
declares `render_cli=True` once on the host rather than on each of the four
declarations — the other direction (per-declaration flags, and a body that
opts out) is what `examplehost` covers.
"""

from __future__ import annotations

from mli import Doc, Host, Skill, typer_app

HOST = Host(
    dist="multihost",
    cli="multihost",
    prompts="multihost.prompts",
    version="0.4.0",
    modes=("local",),
    render_cli=True,
    artifacts=(
        Skill(name="tidy", sources=("skills/tidy.md",)),
        Skill(name="audit", sources=("skills/audit-body.md",)),
    ),
    docs=(
        Doc(name="tidy/fields", source="references/tidy/fields.md"),
        Doc(name="audit/severity", source="references/audit/severity.md"),
    ),
)

app = typer_app(HOST)
