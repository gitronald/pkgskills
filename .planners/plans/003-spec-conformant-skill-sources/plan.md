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

**3-4. Fixtures.** Migrated every source. First pass (`a3c4360`):

| before | after |
| --- | --- |
| `solohost/prompts/skill.md` | `solohost/prompts/skills/use-solo/SKILL.md` |
| `examplehost/prompts/skills/add.md` | `.../skills/add/SKILL.md` |
| `examplehost/prompts/skills/close.md` | `.../skills/close/SKILL.md` |
| `multihost/prompts/skills/tidy.md` | `.../skills/tidy/SKILL.md` |

That pass left `multihost/prompts/skills/audit-body.md` flat, reasoning that
migrating it would erase the property the fixture exists to test — a
single-source skill keyed by `Skill.name` rather than by its source's name —
since a conformant `<name>/SKILL.md` forces directory, frontmatter `name`, and
`Skill.name` to coincide. **Reversed on review:** the point of the plan is a
source tree with no non-conformant sources in it, since the fixtures are what
a host author copies. A second pass (`b54e9d9`) migrated it and went further,
storing the whole skill directory the way the spec describes one rather than
just its entry file:

    multihost/prompts/skills/
    ├── audit/
    │   ├── SKILL.md              # was skills/audit-body.md
    │   └── references/severity.md  # was references/audit/severity.md
    └── tidy/
        ├── SKILL.md
        └── references/fields.md    # was references/tidy/fields.md

A doc's *name* and its *source* are independent, which is what makes this
work: `Doc(name="audit/severity", source="skills/audit/references/severity.md")`
keeps the body writing `{cli} doc audit/severity` while the file lives inside
the skill that owns it. Rules and agents stay flat — they are stamped copies,
not skills — as does `examplehost`'s `references/broken.md`, a deliberately
stale document belonging to no skill.

The keyed-by-`Skill.name` property and flat-source support now live in
`test_skill_bodies_are_keyed_by_source_name_only_when_dispatching`, which
declares an unmigrated `Host` inline (no files needed — `Host.validate` reads
only doc sources) instead of shipping one. That is a real reduction in
coverage: flat *skill* sources are no longer read off disk end to end. The
read path is identical for both layouts and is still exercised by the nested
doc sources, so what is lost is narrow, but it is a trade rather than a wash.

> **Superseded by the review pass below.** `brokenhost` ships a flat skill
> source again — deliberately, as a counterexample — so flat sources *are* read
> off disk end to end once more, and the coverage this paragraph gives up was
> recovered. The paths above also predate the hoist: `multihost`'s skills now
> sit at its prompts root, without the `skills/` segment.

Nested resource paths resolve fine: `Host.read` goes through
`resources.files(...).joinpath(source)`, and every migrated fixture is read
that way by the passing suite. `mli` itself ships no prompts, so the
`wheel_files` test has nothing new to assert.

**5. Layout assertion.** `skills-ref` is not installed and there is no CI hook
for it, so the check is two tests instead, each parametrized over all three
fixture hosts:

- `test_conformant_sources_match_the_spec_layout` — every skill source ends in
  `/SKILL.md` and carries frontmatter whose `name` equals its directory and
  satisfies the spec grammar. Asserting the layout for *every* source, rather
  than only for those already in it, is what makes a silent regression fail
  instead of vacuously passing.
- `test_a_skills_references_live_inside_its_own_directory` — a doc whose name
  is namespaced by a skill the host declares is sourced from under that
  skill's directory. A doc belonging to no skill is exempt.

**"Also worth deciding" — resolved by folding in.** Added
`valid_skill_name(name)` implementing the spec's full `name` grammar (1-64
chars, `[a-z0-9]` and single interior hyphens) and wired it into
`Host.validate` for skills. `Doc.name` is deliberately exempt: a doc is never
installed as a skill and its name may carry `/` for namespacing. `Rule` and
`Agent` are exempt for the reason the plan already gives for their directory
layout — they are stamped copies, not skills.

**6. Docs (`82b74f0`, revised in `b54e9d9`).** New `docs/source-layout.md`
covering the full skill directory (entry file plus its `references/`), how a
source path yields a name, why flat sources still work, what stays flat and
why, and the name grammar; linked from `docs/frontmatter.md` and from the
README's host-authoring section, whose `Skill` and `Doc` examples now use
conformant paths. The README's Documents section gained the name-vs-source
point that makes the layout possible. Added two `[Unreleased]` changelog
entries.

Also swept the now-inaccurate "stem" wording out of `mli/host.py`'s module and
`skill_sources` docstrings, the README's fixtures paragraph, and a local
variable in `mli/cli.py`.

**Checks.** `uv run pytest` (165 passed, 97.77% coverage), `uv run ruff check
.`, `uv run ruff format --check .`, and `uv run pyrefly check` (0 errors) all
pass. Smoke-tested `multihost` directly too: both skill bodies and both docs
render from their new paths with `{cli}` resolved.

### 2026-09-09 — review pass: hoisting, and the spec as a module

Two follow-ups from review, beyond the plan's original scope.

**Hoisting `skills/` (`2655a40`).** `mli` never looks for a `skills/` segment —
only the last two path components matter — so the group is a convenience for
telling skills apart from rules and agents, not a requirement. `solohost` and
`multihost` ship nothing else, so their skills moved to the prompts root
(`solohost/prompts/use-solo/SKILL.md`, `multihost/prompts/tidy/SKILL.md`).
`examplehost` keeps `skills/`, since it has `rules/` and `agents/` beside them;
between them the fixtures now cover both arrangements.

`examplehost/prompts/references/broken.md` was the last thing outside a skill
directory. It is a deliberately stale document used by the negative test for
`assert_prompt_commands`, so it had nowhere conformant to go — attaching it to
a real skill would misrepresent it, and leaving it put kept a stray
`references/` in an otherwise exemplary tree.

**`brokenhost`.** Hence a fourth fixture whose entire purpose is to be wrong.
The other three are exemplary — what they ship is what a host author copies —
which left nowhere to keep the failing cases, and negative tests need real
files: a violation reported off a hand-built string proves the message renders,
not that the check finds anything on disk. `brokenhost` holds the stale-prose
doc, a flat skill source, and a `misfiled/SKILL.md` whose `name` is neither the
spec's grammar nor its directory. Its `__init__` says so, so nobody copies it.

**`mli/spec.py`.** The Agent Skills specification as data rather than as
scattered conditionals:

- `SkillSpec` carries the entry filename, the optional directories
  (`scripts/`, `references/`, `assets/`), the `name` grammar, and every
  frontmatter field as a `Field(name, required, constraint, max_length)`. It is
  a frozen dataclass with `SPEC` as the shipped instance, so a caller can
  `dataclasses.replace` it to pin a different reading without forking the
  checks.
- A departure is a `Violation(where, rule, detail, fix)` — a stable slug to
  filter on, what is actually wrong, and what to do. `SpecError` (a
  `ValueError`, so existing `except ValueError` keeps working) carries them as
  data rather than only as a message.
- `SkillSpec.structure()` renders the spec's own directory diagram, which the
  `entry-file` violation quotes inline. The fix text for
  `name-matches-directory` deliberately never advises renaming a directory to a
  name the grammar rejects — that would trade one violation for two.

Wired in at the three moments a problem can surface:

| When | Checked | Fails as |
| --- | --- | --- |
| `Host(...)` construction | declared `Skill.name`s, all at once | `SpecError` |
| `render` / `install` | the source behind a single-source stub | `SpecError` |
| `assert_spec_conformant(host)` | every skill, every source, read | `AssertionError` |

Construction reads no files on purpose: a host is declared at import time, so
walking the prompt package there would put a file scan on every CLI
invocation. `Host.check_spec()` is the deliberate, file-reading call;
`mli.testing.assert_spec_conformant` is its one-line form for a host's own
suite, the counterpart to `assert_prompt_commands` and there for the same
reason. `stub_frontmatter`'s three ad-hoc `ValueError`s were replaced by the
spec check, so a bad source now reports every problem it has instead of the
first one that function tripped over.

Not checked, and said so in the module docstring: the shape of `metadata`. The
spec makes it a map of string to string and `mli.frontmatter` parses flat
scalars only, so there is nothing to inspect from here. `skills-ref validate`
remains the full check; this is the subset `mli` can enforce from inside a host.

**Tests.** New `tests/test_spec.py` (31 tests, `mli/spec.py` at 100%) covering
the spec-as-data, the layout and name predicates, each frontmatter rule, the
whole-host collection against `brokenhost`, the report formatting, and that the
three exemplary fixtures stay silent. `test_a_skills_references_live_inside_its_own_directory`
now reads each skill's directory off its own source rather than assuming a
`skills/` prefix.

**Docs.** `docs/source-layout.md` gained "The `skills/` group is optional" and
"Checking a host against the spec"; the README's host-authoring and
"Testing a host" sections and `.claude/CLAUDE.md`'s structure map were updated.
Two more `[Unreleased]` changelog entries.

**Checks.** `uv run pytest` (196 passed, 98.15% coverage), ruff check, ruff
format --check, and pyrefly (0 errors) all pass.
