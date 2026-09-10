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

## Log

### 2026-09-09 — implementation

Worked on `feature/spec-conformant-skill-sources` in a worktree. The repo has
no git remote, so there is no PR and nothing was pushed.

**1-2. Source naming (`a3c4360`).** Replaced `_stem` with a public
`source_name(source)` that returns the parent directory when the file is
named exactly `SKILL.md` (with a non-empty parent) and the stem otherwise. The
match is case-sensitive, as the spec writes it uppercase — `skill.md` falls
through to the stem. `Skill.subcommands` and `Skill.source_for` both route
through it, so the duplicate guard and `Host.skill_bodies`' collision check
operate on the derived name automatically; only the error text changed
("duplicate stems" -> "duplicate names").

**3-4. Fixtures.** Migrated three of the four sources:

| before | after |
| --- | --- |
| `solohost/prompts/skill.md` | `solohost/prompts/skills/use-solo/SKILL.md` |
| `examplehost/prompts/skills/add.md` | `.../skills/add/SKILL.md` |
| `examplehost/prompts/skills/close.md` | `.../skills/close/SKILL.md` |
| `multihost/prompts/skills/tidy.md` | `.../skills/tidy/SKILL.md` |

**Deviation from the plan's step 3:** `multihost/prompts/skills/audit-body.md`
was left flat. The plan listed it for migration, but moving it to
`audit-body/SKILL.md` would have made it *non*-conformant — its frontmatter
`name` is `audit` (to match the skill), which would then disagree with the
directory. Naming the directory `audit` instead would have destroyed the exact
property the fixture exists to test: that a single-source skill is keyed by
`Skill.name`, not by its source's name. Leaving it flat preserves that and
simultaneously satisfies step 4's requirement that an unmigrated flat source
stay covered — `multihost` now carries both layouts side by side, which is
better coverage than either alone.

Nested resource paths resolve fine: `Host.read` goes through
`resources.files(...).joinpath(source)`, and every migrated fixture is read
that way by the passing suite. `mli` itself ships no prompts, so the
`wheel_files` test has nothing new to assert.

**5. Layout assertion.** `skills-ref` is not installed and there is no CI hook
for it, so the check is a test instead:
`test_conformant_sources_match_the_spec_layout` is parametrized over all three
fixture hosts and asserts that every source ending in `/SKILL.md` has
frontmatter whose `name` equals its directory and satisfies the spec grammar.
It also asserts each host ships at least one conformant source, so a
regression that quietly reverted the layout would fail rather than vacuously
pass.

**"Also worth deciding" — resolved by folding in.** Added
`valid_skill_name(name)` implementing the spec's full `name` grammar (1-64
chars, `[a-z0-9]` and single interior hyphens) and wired it into
`Host.validate` for skills. `Doc.name` is deliberately exempt: a doc is never
installed as a skill and its name may carry `/` for namespacing. `Rule` and
`Agent` are exempt for the reason the plan already gives for their directory
layout — they are stamped copies, not skills.

**6. Docs (`82b74f0`).** New `docs/source-layout.md` covering the conformant
layout, how a source path yields a name, why flat sources still work, and the
name grammar; linked from `docs/frontmatter.md` and from the README's
host-authoring section, whose example now uses the conformant paths. Added two
`[Unreleased]` changelog entries.

Also swept the now-inaccurate "stem" wording out of `mli/host.py`'s module and
`skill_sources` docstrings, the README's fixtures paragraph, and a local
variable in `mli/cli.py`.

**Checks.** `uv run pytest` (162 passed, 97.77% coverage), `uv run ruff check
.`, `uv run ruff format --check .`, and `uv run pyrefly check` (0 errors) all
pass.
