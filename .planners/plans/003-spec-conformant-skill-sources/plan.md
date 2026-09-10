---
id: 3
slug: spec-conformant-skill-sources
status: active
branch: feature/spec-conformant-skill-sources
created: 2026-09-09T21:51:26-07:00
concluded:
pr:
---

# Store skill sources as spec-conformant SKILL.md directories

## Plan

### Problem

The Agent Skills specification requires a skill's frontmatter `name` to **match
its parent directory name** (`docs/agentskills-specification.md`, under the
`name` field constraints). A conformant skill is a directory:

```
use-solo/
└── SKILL.md
```

Every prompt source a host ships today is a flat file whose `name` cannot
match its parent, so a host package's `prompts/` tree is not spec-conformant
and a skills linter pointed at it reports naming-convention errors:

| source | frontmatter `name` | parent dir |
| --- | --- | --- |
| `solohost/prompts/skill.md` | `use-solo` | `prompts` |
| `examplehost/prompts/skills/add.md` | `add` | `skills` |
| `examplehost/prompts/skills/close.md` | `close` | `skills` |
| `multihost/prompts/skills/tidy.md` | `tidy` | `skills` |

The installed side is already conformant — `.claude/skills/{name}/SKILL.md`
(`mli/harness.py`) and the frontmatter both derive from `skill.name`, and
`stub_frontmatter` rejects a source whose declared `name` disagrees. Only the
source side is at issue.

### Blocker

`mli` cannot currently store sources in that layout. `Skill.subcommands`
derives a dispatcher's subcommand names from the source file's **stem**
(`mli/host.py`, via `_stem` = `PurePosixPath(source).stem`). Under the
conformant layout every stem becomes the literal `SKILL`, so:

- a dispatcher's subcommands all collapse to `SKILL`;
- `Host.__post_init__` rejects the host with "has sources with duplicate
  stems";
- `Skill.source_for` can no longer route a subcommand to its body.

### Approach

Fix at the source: change how a source path yields its name, rather than
renaming files to work around the stem rule.

1. **Rework `_stem` in `mli/host.py`** into a source-name helper that returns
   the **parent directory name** when the file is `SKILL.md`, and the file
   stem otherwise. This keeps every existing flat-file host working unchanged
   while making the conformant layout expressible.
   - Decide whether the `SKILL.md` match is case-sensitive; the spec writes it
     uppercase, so match exactly and let anything else fall through to the stem.
   - A source of `skills/use-solo/SKILL.md` then yields `use-solo`.
2. **Restore the duplicate check's meaning.** The existing duplicate-stem
   guard and the `body_names` collision check in `Host.skill_bodies` should
   operate on the new derived name, so two sources under different directories
   named `SKILL.md` are distinguished rather than rejected.
3. **Restructure the test fixtures** under `tests/fixtures/` into the
   conformant layout, updating each host's declared `sources`:
   - `solohost/prompts/skills/use-solo/SKILL.md`
   - `examplehost/prompts/skills/add/SKILL.md`, `.../close/SKILL.md`
   - `multihost/prompts/skills/tidy/SKILL.md`, `.../audit-body/SKILL.md`
   - Confirm the prompt package still resolves nested resource paths (the
     package data must include the new directories).
4. **Keep flat sources supported.** A host that has not migrated must keep
   working, so retain coverage for a flat source alongside the new fixtures —
   the change is additive, not a cutover.
5. **Validate the fixtures against the spec** if `skills-ref validate` can be
   run in CI or locally; otherwise assert the layout in a test (every skill
   source is `<name>/SKILL.md` with matching frontmatter).
6. **Document it** — record the required source layout in `docs/` (alongside
   `docs/frontmatter.md`, which already covers what the stub's frontmatter
   carries) and in the README's host-authoring guidance.

### Also worth deciding

`Skill.name` is a bare `str` with no format validation
(`mli/host.py`). The spec's other `name` rules — 1-64 characters, lowercase
`a-z0-9` and hyphens only, no leading/trailing hyphen, no consecutive hyphens
— are unenforced, so a host can declare a spec-invalid skill name and `mli`
will happily install it. Either fold that validation into this plan's
`Host.__post_init__` work or split it into a follow-up plan.

### Out of scope

- Changing the installed artifact layout, which is already conformant.
- Renaming or restructuring rule and agent sources; they are stamped copies,
  not skills, and the spec's directory rule does not apply to them.

### Implementation order

1 -> 2 -> 3 -> 4 -> 5 -> 6, with the fixture restructure (3) as the point where
the change is proven end to end.
