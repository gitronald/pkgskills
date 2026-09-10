# Source layout

How a host arranges the prompt files it ships, and what `mli` reads out of
their paths.

The [Agent Skills specification](agentskills-specification.md) makes a skill a
*directory*: a `SKILL.md` entry file whose frontmatter `name` must match the
parent directory's name. The installed side has always satisfied that —
`install` writes `.claude/skills/{name}/SKILL.md` and both the directory and
the frontmatter derive from the same `Skill.name`. This page is about the other
side: the sources inside the host package.

## The conformant layout

Give each skill source its own directory, named for the skill:

```
yourtool/
└── prompts/
    ├── skills/
    │   ├── add/
    │   │   └── SKILL.md      # frontmatter: name: add
    │   └── close/
    │       └── SKILL.md      # frontmatter: name: close
    ├── references/
    │   └── add/fields.md
    └── rules/yourtool.md
```

```python
Skill(name="yourtool", sources=("skills/add/SKILL.md", "skills/close/SKILL.md"))
```

A `prompts/` tree in this shape passes a skills linter as it stands, because
every source is a skill directory with a matching `name`.

## How a source gets its name

`mli` needs a name per source: a dispatcher advertises one subcommand per
source, and `<cli> skill <subcommand>` routes back to the body behind it.

That name is the source's **parent directory** when the file is named exactly
`SKILL.md`, and the file **stem** otherwise. So `skills/add/SKILL.md` names
`add`, and `skills/audit-body.md` names `audit-body`. The match on `SKILL.md`
is exact — the spec writes it uppercase, and `skill.md` or `Skill.md` is
treated as an ordinary flat file named by its stem.

Two sources of one skill may not resolve to the same name; `Host` rejects that
at construction, as it rejects a dispatcher name that collides with another
skill's own name.

## Flat sources still work

Nothing forces the migration. A host that ships `skills/tidy.md` keeps working
exactly as before — the stem names it — and a host may mix the two layouts.
The only thing the flat layout costs is spec conformance of the source tree
itself, which matters when a linter is pointed at the package.

The name a source contributes is not the name a *single-source* skill is
addressed by. That one answers to `Skill.name` — what the stub's frontmatter
and the slash command say — so its file may be called anything:

```python
Skill(name="audit", sources=("skills/audit-body.md",))  # `<cli> skill audit`
```

Only a dispatcher's subcommands come from the source paths.

## Skill names

`Skill.name` is validated against the spec's grammar at construction: 1-64
characters of `a-z`, `0-9`, and hyphens, with no leading, trailing, or
consecutive hyphen. It becomes both the installed directory name and the stub's
frontmatter `name`, so a name the spec rejects would install a skill the
harness may refuse to load.

`Doc.name` is deliberately *not* held to that grammar: a doc is never installed
as a skill, and its name may carry a `/` so a host can namespace its references
by the skill that owns them (`add/fields`).

## Related

- [Frontmatter](frontmatter.md) — what `mli` writes into a generated stub's
  frontmatter, and the rules for a source prompt's own.
