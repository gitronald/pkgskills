"""A throwaway host with two single-source skills and no dispatcher.

The shape the other two fixtures leave untested: several skills, each with one
body and one trigger. `audit` deliberately lives in a file whose stem is not
its skill name, so keying bodies by stem would break it while `tidy` kept
working.
"""

from __future__ import annotations

from mli import Host, Skill, typer_app

HOST = Host(
    dist="multihost",
    cli="multihost",
    prompts="multihost.prompts",
    version="0.4.0",
    artifacts=(
        Skill(name="tidy", sources=("skills/tidy.md",), render_cli=True),
        Skill(name="audit", sources=("skills/audit-body.md",), render_cli=True),
    ),
)

app = typer_app(HOST)
