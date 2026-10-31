# Source layout

How a host arranges the prompt files it ships, and what `pkgskills` reads out of
their paths.

The [Agent Skills specification](https://agentskills.io/specification) makes a
skill a *directory*: a `SKILL.md` entry file whose frontmatter `name` must
match the parent directory's name. The installed side has always satisfied that —
`install` writes `.claude/skills/{name}/SKILL.md` and both the directory and
the frontmatter derive from the same `Skill.name`. This page is about the other
side: the sources inside the host package.

## The conformant layout

Store each skill as the spec stores one: a directory named for the skill,
holding its `SKILL.md` **and** whatever else belongs to it — `references/`,
`scripts/`, `assets/`.

```
yourtool/
└── prompts/
    ├── skills/
    │   ├── add/
    │   │   ├── SKILL.md              # frontmatter: name: add
    │   │   └── references/fields.md
    │   └── close/
    │       └── SKILL.md              # frontmatter: name: close
    ├── rules/yourtool.md
    └── agents/reviewer.md
```

```python
HOST = Host(
    ...,
    artifacts=(
        Skill(
            name="yourtool",
            sources=("skills/add/SKILL.md", "skills/close/SKILL.md"),
        ),
    ),
    docs=(Doc(name="add/fields", source="skills/add/references/fields.md"),),
)
```

A `prompts/` tree in this shape passes a skills linter as it stands, because
every skill is a directory with a matching `name` and nothing of a skill's
sits outside it.

A `Doc`'s **name** and its **source** are independent, which is what lets this
work: the name is the argument a body writes (`{cli} doc add/fields`), while
the source is where the file is stored. Namespacing the name by the owning
skill and storing the file inside that skill's directory are the same
convention seen from the two ends.

Rules and agents are not skills — the harness reads their full text off disk
with no model in the loop, and the spec's directory rule does not reach them —
so they stay flat files under `rules/` and `agents/`. A reference that belongs
to no skill has nowhere to live either, and stays wherever the host puts it.

### The `skills/` group is optional

`pkgskills` never looks for a `skills/` segment; a source's path matters only in
that its last two components are `<name>/SKILL.md`. The group earns its keep
when a host ships rules or agents too, and it is noise when a host ships only
skills:

```
yourtool/
└── prompts/
    ├── tidy/SKILL.md
    └── audit/SKILL.md
```

```python
artifacts = (
    Skill(name="tidy", sources=("tidy/SKILL.md",)),
    Skill(name="audit", sources=("audit/SKILL.md",)),
)
```

Both arrangements are conformant. Pick whichever leaves the tree readable.

## How a source gets its name

`pkgskills` needs a name per source: a dispatcher advertises one subcommand per
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
itself, which matters when a linter is pointed at the package or when a host's
suite calls `assert_spec_conformant`. `pkgskills`'s own
exemplary fixture hosts are all conformant, since what they ship is what a host
author copies; the flat layout lives in `brokenhost`, the fixture whose whole
purpose is to be wrong, and in tests that declare it inline.

Working is not the same as passing. `assert_spec_conformant` asserts the whole
spec, and the layout is part of it (the `entry-file` rule), so a host that adopts
the helper as written uses the directory layout, a dispatcher's sources included.

A host that keeps flat sources on purpose asserts everything else by filtering
the report, which leaves the exception visible in its own test:

```python
def test_prompts_are_well_formed() -> None:
    violations = [v for v in HOST.check_spec() if v.rule != "entry-file"]
    assert not violations, "\n".join(map(str, violations))
    assert_prompt_commands(HOST, app)
```

The rule does not vary by what a source is for. Neither a dispatcher's source nor
a single-source skill's is installed where it sits: what installs is the stub, at
a path built from `Skill.name`, so a flat source of either kind produces a
conformant installed skill. The layout matters only to something reading the
package, and that reader cannot tell the two kinds apart.

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

## Checking a host against the spec

`pkgskills.spec` holds the specification as data — the entry filename, the
optional directories, every frontmatter field with its limit, and the `name`
grammar — on a `SkillSpec` dataclass, with `pkgskills.SPEC` as the instance
everything uses. Holding it as data rather than as scattered conditionals is
what lets a failure say which rule broke and what to do:

```
brokenhost ships skills that do not follow the Agent Skills specification
(skills-ref validate checks the same rules):
  misfiled/SKILL.md:
    - frontmatter declares no `description` [description-missing] -- add
      `description`: 1-1024 characters saying what the skill does and when to use it
    - frontmatter names 'Misfiled Skill' but the directory is 'misfiled'; the
      spec requires they match [name-matches-directory] -- set the `name` to 'misfiled'
```

Three surfaces report it, at the three moments a problem can be caught:

| When | What is checked | How it fails |
|---|---|---|
| `Host(...)` construction | declared `Skill.name`s only | raises `SpecError` |
| `install` / `render` | the source behind a single-source skill's stub | raises `SpecError` |
| `assert_spec_conformant(host)` | every skill, every source, read | `AssertionError` |

Construction deliberately reads no files: a host is declared at import time, so
walking the prompt package there would put a file scan on every invocation of
the CLI. `Host.check_spec()` returns the full list of `Violation`s for a caller
that wants them as data, and `pkgskills.testing.assert_spec_conformant(host)` is
the one-line form for a host's own test suite — the counterpart to
`assert_prompt_commands`, and there for the same reason: what a host bundles is
read by a harness and by whatever linter a consumer points at the package, and
neither of those is running while the host's suite is.

```python
from pkgskills.testing import assert_prompt_commands, assert_spec_conformant


def test_prompts_are_well_formed() -> None:
    assert_spec_conformant(HOST)
    assert_prompt_commands(HOST, app)
```

Every violation is reported at once rather than one per run, because a source
that is wrong in one way is usually wrong in two. Each carries a stable `rule`
slug (`entry-file`, `name-grammar`, `name-matches-directory`,
`description-missing`, ...) so a caller can filter rather than parse prose.

`metadata` is checked too. The spec calls it *a map from string keys to string
values*, and the rule that earns its keep is the value one — the spec's own
example writes `version: "1.0"` with the quotes because unquoted it is a float:

```yaml
metadata:
  author: example-org   # fine: a plain scalar is still a string
  version: 1.0          # metadata-value-not-a-string: YAML reads a float
  retries: 3            # ...an integer
  enabled: true         # ...a boolean
  owner:                # ...and a nested mapping is not a string at all
    team: platform
```

`pkgskills.frontmatter.parse_fields` flattens a nested block, so the check
parses the raw frontmatter with YAML itself and reads the mapping from there. `pkgskills` splices nothing into `metadata` of its own: a single-source
stub lifts whatever the source declares, `version` included, byte for byte, and a
dispatcher stub [declares none](frontmatter.md#a-dispatchers-sources). The check
still covers a dispatcher's sources, because a linter reads them too.

Which bare versions pass, and why to quote them anyway, is in
[Frontmatter](frontmatter.md#what-a-stub-carries).

What is *not* checked is the spec's **recommendations**, as against its
constraints: that a description say what a skill does *and* when to use it,
that `SKILL.md` stay under 500 lines, that references sit one level deep. Those
are advice to an author, and failing a host over them would assert a house
style the specification does not. The reference validator the spec ships,
`skills-ref validate`, remains the tool for a full check.

## Related

- [Frontmatter](frontmatter.md) — what `pkgskills` writes into a generated
  stub's frontmatter, and the rules for a source prompt's own.
