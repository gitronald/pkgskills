# Frontmatter

What `pkgskills` writes into the frontmatter of a generated skill stub, and why.

The shape is fixed by the [Agent Skills
specification](https://agentskills.io/specification), which defines the fields and
reserves `metadata` for properties it does not itself define, recommending
reasonably unique key names.

## What a stub carries

```yaml
---
name: use-solo
description: Use solohost to look things up. Triggers on "look up" or "is this real?".
metadata:
  version: "0.9.0"
  pkgskills-version: "0.1.0a0"
---
```

- `name` and `description` come from the skill's source prompt, or — for a
  dispatcher — are generated from the declaration. They are the only fields the
  harness reads to decide when a skill fires.
- `metadata.version` is the **host release** the stub was rendered from: the
  skill's own version, and the key the spec's own example uses.
- `metadata.pkgskills-version` is the `pkgskills` release that rendered it,
  prefixed because it belongs to a second package.

Both values are quoted. A version is a string, and an unquoted `1.0` reads back
as a float.

## Why both the metadata and the stamp

Every generated file already carries an HTML-comment stamp naming the same two
versions plus the mode and the repair command. The stamp stays the contract —
it is what `install --check` matches on, it works for rules and agents (which
are not skills and have no `metadata` field), and it survives in file kinds
where frontmatter would not.

The `metadata` entries are a mirror of it in the spec's own vocabulary, so a
tool that parses only the frontmatter — a skill registry, a linter, another
harness — can still tell which release it is looking at without knowing
anything about `pkgskills`'s comment format.

Rules and agents are unchanged: they are stamped copies, and their source
frontmatter is passed through untouched.

## Drift and masking

`install --check` masks every version token before comparing, in the metadata
as well as the stamp, so upgrading either package never reports drift on a file
whose content did not change. The metadata pattern is anchored to a
two-space-indented line with a quoted value — the exact shape `pkgskills`
writes.

## Writing a source prompt

- Do not put `version` or `pkgskills-version` under `metadata` in a source
  prompt. `pkgskills` writes those keys, and a source that also declares one is
  rejected with an error rather than emitted as a duplicate YAML key.
- Any other `metadata` keys a source declares are kept; `pkgskills`'s two
  entries are inserted at the top of the mapping.
- A source that declares no `metadata` gets the block opened for it, just
  before the closing fence. Every other line of the block is copied byte for
  byte.
- Where the source file itself belongs, and how its path names it, is
  [Source layout](source-layout.md).
