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
---
```

`pkgskills` writes **none** of it. A single-source stub lifts its source's
frontmatter block byte for byte; a dispatcher generates `name` and
`description` from the declaration and nothing else.

- `name` and `description` come from the skill's source prompt, or — for a
  dispatcher — are generated from the declaration. They are the only fields the
  harness reads to decide when a skill fires.
- `metadata.version`, when present, is the **skill's own** version, declared and
  maintained by the source. It is what the spec's own example implies the key
  means. A source that declares no version gets no `version` key, and a source
  that declares no `metadata` at all gets no `metadata` mapping — there is no
  fallback to the host release.

Quote the value. A version is a string, and an unquoted `1.0` reads back as a
float and fails `assert_spec_conformant` (`metadata-value-not-a-string`), as do
`1` and a bare date. A bare `1.0.0` happens to read as a string and passes, but
quote it anyway: the same key becomes a float the day it reads `2.0`.

## A dispatcher's sources

A dispatcher stub declares no `metadata`. It has one frontmatter block and
several sources, and it takes only each source's `description`, for its list of
subcommands. A `metadata` block on a dispatcher source is therefore the source's
own: the conformance check reads it, and so does a linter or a person looking
at the package, but it reaches no installed file. Adding one or bumping a
version in it leaves the stub unchanged, so nothing drifts.

Set it if those readers are worth it, and quote it the same way, since the
check covers every source. The release of a dispatcher as a whole is the host's,
and the stamp already records that.

## Where the release provenance lives

In the stamp, and only there. Every generated file carries an HTML-comment
stamp naming the host distribution and its release, the `pkgskills` release, the
mode, and the repair command. It is what `install --check` matches on, it works
for rules and agents (which are not skills and have no `metadata` field), and
it survives in file kinds where frontmatter would not.

Mirroring it into `metadata` would mean one key answering two questions — the
host's release or the skill's — depending on the source. The stamp is one line
below the block; a reader who wants the release reads it there.

Rules and agents are unchanged: they are stamped copies, and their source
frontmatter is passed through untouched.

## Drift and masking

`install --check` masks the two version tokens in the stamp line before
comparing, so upgrading either package never reports drift on a file whose
content did not change. A `metadata.version` in a single-source stub is *not*
masked: it is the skill's own, so changing it is a real content change and the
stub should drift until it is reinstalled.

## Writing a source prompt

- Declare `metadata.version` if the skill is versioned on its own schedule, and
  leave it out if it is not. `pkgskills` writes no metadata keys, so nothing it
  emits can collide with what the source declares.
- Every `metadata` key a single-source skill declares is kept, in the order the
  source wrote them. A [dispatcher's sources](#a-dispatchers-sources) keep theirs
  in the package.
- Where the source file itself belongs, and how its path names it, is
  [Source layout](source-layout.md).
