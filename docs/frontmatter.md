# Frontmatter

What ends up in the frontmatter of a generated skill stub, and why.

The shape is fixed by the [Agent Skills
specification](https://agentskills.io/specification), which defines the fields and
reserves `metadata` for properties it does not itself define, recommending
reasonably unique key names.

## What a stub carries

```yaml
---
name: audit
description: Audit a workspace with multihost. Triggers on "audit" or "what drifted?".
metadata:
  version: "2.1"
  pkgskills-host: "multihost"
  pkgskills-host-version: "0.4.0"
  pkgskills-version: "0.5.1"
  pkgskills-mode: "local"
  pkgskills-note: "generated; install overwrites edits"
---
```

`pkgskills` writes only the `pkgskills-*` keys. A single-source stub lifts its
source's frontmatter block byte for byte and adds them after the source's own
`metadata` keys, opening a `metadata` map when the source has none. A dispatcher
generates `name` and `description` from the declaration, then adds the same keys.

- `name` and `description` come from the skill's source prompt, or — for a
  dispatcher — are generated from the declaration. They are the only fields the
  harness reads to decide when a skill fires.
- `metadata.version`, when present, is the **skill's own** version, declared and
  maintained by the source. It is what the spec's own example implies the key
  means. A source that declares no version gets no `version` key — there is no
  fallback to the host release, which `pkgskills-host-version` records.
- The `pkgskills-*` keys are the [provenance
  stamp](#where-the-release-provenance-lives).

Quote the value. A version is a string, and an unquoted `1.0` reads back as a
float and fails `assert_spec_conformant` (`metadata-value-not-a-string`), as do
`1` and a bare date. A bare `1.0.0` happens to read as a string and passes, but
quote it anyway: the same key becomes a float the day it reads `2.0`.

## A dispatcher's sources

A dispatcher stub's `metadata` holds only the stamp. It has one frontmatter block
and several sources, so what it takes from each source goes in the body, as a row of
its subcommand table: the `description`, and `metadata.version` in the Version
column.

```markdown
| Subcommand | Version | Description |
|---|---|---|
| `add` | 1.0.0 | Scaffold a new plan file. |
| `close` |  | Close a finished plan. |
```

A source that declares no version gets an empty cell, for the same reason a
single-source stub gets no `version` key: the release of a dispatcher as a whole
is the host's, and the stamp already records that. The version is the source's own
text, so adding one or bumping it drifts the stub until it is reinstalled.

Any other `metadata` key on a dispatcher source reaches no installed file. The
conformance check reads it, and so does a linter or a person looking at the
package, so set it if those readers are worth it. Quote a version the same way,
since the check covers every source.

## Where the release provenance lives

In the stamp, and only there. Every generated file carries five keys under
`metadata`, each a quoted string:

| Key | What it records |
|---|---|
| `pkgskills-host` | the host distribution |
| `pkgskills-host-version` | the host's release |
| `pkgskills-version` | the `pkgskills` release that rendered the file |
| `pkgskills-mode` | the install mode, `global` or `local` |
| `pkgskills-note` | a fixed warning that a bare `install` overwrites edits |

It is what `install --check` matches on. The command that repairs a file is not
in it, because that follows from the host and the mode: a stub's body prints it,
and `install --check` prints what each row that is not `ok` needs.

They are under `metadata`, not in a top-level key of their own, because the
specification leaves that map for "additional properties not defined by the
Agent Skills spec", and its reference validator, `skills-ref validate`, rejects
any other top-level key. The prefix keeps them from meaning anything to a source:
`metadata.version` stays the skill's own, answering one question.

Rules and agents carry the same keys, though they are not skills. A source with
no frontmatter gains a block, and a source with one keeps it, `paths` included,
with the keys added after its own. Claude Code strips frontmatter from a rule
before injecting it, and takes a skill's into its own index, so the stamp costs
no context. That it ignores keys it does not document was observed on a rule, and
is not a guarantee.

A file installed by an earlier release has the stamp as an HTML comment instead.
`pkgskills` still recognizes that line: the file reads `drifted`, and a bare
`install` rewrites it in the new form. Nothing writes the comment any more.

## Drift and masking

`install --check` masks the values of `pkgskills-host-version` and
`pkgskills-version` before comparing, so upgrading either package never reports
drift on a file whose
content did not change. A source's `metadata.version` is *not* masked, whether it
rides in a single-source stub's frontmatter or a dispatcher's table: it is the
skill's own, so changing it is a real content change and the stub should drift
until it is reinstalled.

## Writing a source prompt

- Declare `metadata.version` if the skill is versioned on its own schedule, and
  leave it out if it is not.
- Leave the `pkgskills-` prefix alone. `pkgskills` writes those keys, so a source
  declaring one fails `assert_spec_conformant` (`metadata-key-reserved`) and cannot
  be rendered. The rule covers rules and agents as well as single-source skills.
- In a rule or agent, keep any frontmatter a YAML mapping, with `metadata` a
  mapping if it is there, so the stamp can join it. A source that is not fails
  the same way.
- In any source that reaches an installed file, avoid a block the keys cannot join
  without changing what it says: a flow-style root, a `metadata` that is a YAML
  alias of another key, or a keep-chomped scalar at the end of `metadata`. It fails
  `assert_spec_conformant` (`stamp-cannot-join`) and cannot be rendered.
- Every `metadata` key a single-source skill declares is kept, in the order the
  source wrote them. A [dispatcher's sources](#a-dispatchers-sources) keep theirs
  in the package, apart from the version its table shows.
- Where the source file itself belongs, and how its path names it, is
  [Source layout](source-layout.md).
