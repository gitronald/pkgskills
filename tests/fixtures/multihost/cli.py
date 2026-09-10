"""A throwaway host with two single-source skills and no dispatcher.

The shape the other two fixtures leave untested: several skills, each with one
body and one trigger. It is also where the two source layouts sit side by side.
`tidy` ships the spec-conformant `skills/tidy/SKILL.md`, while `audit`
deliberately stays a flat file whose name is neither `SKILL.md` nor its own
skill name — so keying bodies by source name would break it while `tidy` kept
working, and an unmigrated host stays covered. It is also the local-only host:
its skills only mean anything inside one repository, so it declares
`modes=("local",)` and global mode is unreachable for it.

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
        Skill(name="tidy", sources=("skills/tidy/SKILL.md",)),
        Skill(name="audit", sources=("skills/audit-body.md",)),
    ),
    docs=(
        Doc(name="tidy/fields", source="references/tidy/fields.md"),
        Doc(name="audit/severity", source="references/audit/severity.md"),
    ),
)

app = typer_app(HOST)
