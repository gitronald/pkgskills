# Frontmatter

What `mli` writes into the frontmatter of a generated skill stub, and why.

The shape is fixed by the Agent Skills specification — a local copy lives at
[agentskills-specification.md](agentskills-specification.md), and the canonical
version at
[agentskills.io/specification](https://agentskills.io/specification#frontmatter-required).
`name` and `description` are required; `license`, `compatibility`, `metadata`,
and `allowed-tools` are optional. `metadata` is "a map from string keys to
string values" that clients may use for properties the spec does not define,
with a recommendation to keep key names reasonably unique.

## What a stub carries

```yaml
---
name: use-solo
description: Use solohost to look things up. Triggers on "look up" or "is this real?".
metadata:
  version: "0.9.0"
  mli-version: "0.1.0a0"
---
```

- `name` and `description` come from the skill's source prompt, or — for a
  dispatcher — are generated from the declaration. They are the only fields the
  harness reads to decide when a skill fires.
- `metadata.version` is the **host release** the stub was rendered from: the
  skill's own version, and the key the spec's own example uses.
- `metadata.mli-version` is the `mli` release that rendered it. It is prefixed
  because it belongs to a second package, per the spec's advice on unique key
  names.

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
anything about `mli`'s comment format.

Rules and agents are unchanged: they are stamped copies, and their source
frontmatter is passed through untouched.

## Drift and masking

`install --check` masks every version token before comparing, in the metadata
as well as the stamp, so upgrading either package never reports drift on a file
whose content did not change. The metadata pattern is anchored to a
two-space-indented line with a quoted value — the exact shape `mli` writes.

## Writing a source prompt

- Do not put `version` or `mli-version` under `metadata` in a source prompt.
  `mli` writes those keys, and a source that also declares one is rejected with
  an error rather than emitted as a duplicate YAML key.
- Any other `metadata` keys a source declares are kept; `mli`'s two entries are
  inserted at the top of the mapping.
- A source that declares no `metadata` gets the block opened for it, just
  before the closing fence. Every other line of the block is copied byte for
  byte.
