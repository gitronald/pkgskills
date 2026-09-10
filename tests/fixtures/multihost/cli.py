"""A throwaway host with two single-source skills and no dispatcher.

The shape the other two fixtures leave untested: several skills, each with one
body and one trigger. It is also the local-only host: its skills only mean
anything inside one repository, so it declares `modes=("local",)` and global
mode is unreachable for it.

It ships the reference documents too, and it is where a skill directory is
stored the way the spec describes one — the whole directory, not just its entry
file:

    prompts/skills/
    ├── audit/
    │   ├── SKILL.md
    │   └── references/severity.md
    └── tidy/
        ├── SKILL.md
        └── references/fields.md

So a doc's *name* still namespaces it by the skill that owns it
(`audit/severity`), but its *source* now lives inside that skill's own
directory rather than in a parallel `references/` tree. Every body it has uses
`{cli}`, so it declares `render_cli=True` once on the host rather than on each
of the four declarations — the other direction (per-declaration flags, and a
body that opts out) is what `examplehost` covers.
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
        Skill(name="audit", sources=("skills/audit/SKILL.md",)),
    ),
    docs=(
        Doc(name="tidy/fields", source="skills/tidy/references/fields.md"),
        Doc(name="audit/severity", source="skills/audit/references/severity.md"),
    ),
)

app = typer_app(HOST)
