---
id: 4
slug: per-skill-and-host-versions
status: draft
branch:
created: 2026-09-10T01:17:38-07:00
concluded:
pr:
---

# Decide whether a stub carries a per-skill version and a host-namespaced key

## Plan

### Problem

`mli` owns two frontmatter keys under `metadata` and rejects a source prompt that
declares either. That is deliberate and documented, but it settles a design question
by implication rather than by decision: **a stub's `version` is the host release, so
a skill cannot carry a version of its own.**

It surfaced when a host migrated a set of hand-written skills into a package. Each
source already declared its own `metadata.version`, maintained per skill, and one of
them was deliberately ahead of the rest. All of them had to be dropped to render at
all, so every stub now reports the same host release and the per-skill numbers
survive only in that repo's git history.

The host-release model is defensible — the stamp says which package release the text
came from, which is what a session reading a stub wants to know. It was simply never
weighed against the alternative.

### Current behaviour, for the record

- `stamp.py`: `METADATA_KEYS = ("version", "mli-version")`. `metadata_lines(host)`
  writes `version: "<host.resolved_version()>"` and `mli-version: "<mli_version()>"`,
  both quoted, since the spec makes metadata values strings.
- `rendering.with_metadata` raises `ValueError` naming the offending key when a
  source declares one, rather than emitting a duplicate YAML key.
- `mask_versions` masks both tokens in the stamp line *and* both `metadata` entries
  before a drift comparison, so upgrading either package never reports drift on a
  file whose content did not change.
- Any other `metadata` key a source declares is kept, with mli's entries inserted at
  the top of the mapping.

### The two questions

1. **May a source declare its own per-skill version?** If yes, `version` comes to
   mean the skill's own release and the host's release needs somewhere else to live.
2. **Should the host's release be namespaced as `<dist>-version`?** It would be
   symmetric with `mli-version` and matches the specification's recommendation of
   reasonably unique metadata key names — but it departs from the spec's own example,
   which writes a bare `version`.

These are one design, not two: freeing `version` for the source is exactly what
creates the need for `<dist>-version`, and keeping the host's release in `version` is
what keeps a source-declared one out. Deciding either settles the other.

### What a host can do today

Declare any other key — `mli` keeps it verbatim:

```yaml
metadata:
  skill-version: "0.2.0"
```

Cheap, spec-valid, and available now, so nothing needs to block on this plan.

### Worth weighing when this is taken up

- A key **rename is a content change**, not a masked version token, so every existing
  stub of every host would report drift once and need a `--force` reinstall.
- A source-declared version presumably *should* drift when it changes, unlike the two
  keys `mli` writes. Masking would have to tell the two apart, which it currently has
  no reason to do.

### Out of scope

Changing the behaviour now. This plan records the question; the workaround above is
what gathers the evidence for answering it.

### Implementation order

Take it up when a host actually wants per-skill versions in its stubs. Until then it
stays `draft` on purpose.
