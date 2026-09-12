---
id: 4
slug: per-skill-and-host-versions
status: active
branch: feature/per-skill-and-host-versions
created: 2026-09-10T01:17:38-07:00
concluded:
pr:
---

# Track only a skill-level version in stub metadata

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

### The decision

Both questions are answered by rejecting their shared premise. The pairing above holds
only if the host's release *must* live in the frontmatter, and it does not: the stamp
already names the host distribution, its release, the `pkgskills` release, and the mode,
one line below the block. `stamp.py`'s own docstring concedes as much — *"The stamp
remains the contract; the metadata mirrors it."* The stated reason for mirroring, that a
tool reading the frontmatter alone can still tell which release it is looking at, is thin
when the authoritative copy is two lines away.

So the third key never has to exist, and the answer is **one version key, owned by the
source**:

- **the stamp** stays the sole home of provenance — host distribution and release,
  `pkgskills` release, mode, regeneration command. Unchanged.
- **`metadata.version`** becomes the skill's own version, declared by the source and
  passed through verbatim.
- **`pkgskills-version`** is dropped from a stub's `metadata` entirely.
- **a source that declares no version** gets no `version` key, and no `metadata` mapping
  at all if it declares nothing else. There is no fallback to the host release: a
  fallback would make one key mean two different things depending on the source, which
  is the ambiguity this removes, and the stamp already answers "which release is this".

This also aligns the key with what the specification's example implies `metadata.version`
means — the skill's version — which the host-release reading quietly repurposes.

### What it deletes

The change is a net simplification, not a swap. Nothing replaces what comes out.

- `stamp.py`: `METADATA_KEYS`, `_META_RE`, `metadata_lines`, and the metadata half of
  `mask_versions`. A source-owned version *should* drift when it changes, so there is
  nothing left to mask; `mask_versions` goes back to being only about the stamp line.
  Masking never has to tell a source-declared key from a generated one, because
  `pkgskills` stops writing one.
- `rendering.py`: `with_metadata` goes away entirely rather than shrinking. A
  single-source stub lifts the source's frontmatter block, which already carries whatever
  `metadata` the source declared, so the splice is a no-op; a dispatcher generates its own
  block and has no source version to carry. Its collision `ValueError` has nothing left to
  collide with, and its inline-`metadata` `SpecError` is redundant — `stub_frontmatter`
  already calls `SPEC.check_parsed`, which runs `check_metadata`, which reports the same
  violation first.
- `spec.py`: `check_metadata_block` stays (it is `check_metadata`'s worker), but its
  docstring cites `with_metadata` as the caller that splices, and must stop.
- `tests/test_render.py`: the two collision tests and
  `test_mask_versions_covers_the_stubs_metadata_versions` go; add coverage for a
  source-declared `version` surviving into the stub verbatim, for a versionless source
  producing no `metadata` mapping, and for a source `version` change *drifting* rather
  than being masked.

### Migration

Removing a key is a content change, not a masked token, so every existing stub reports
drift once and needs a `--force` reinstall. That cost is a function of how many hosts
exist, and only grows — at `0.2.x` with a very small host set it is close to free, which
is the argument for doing it now rather than banking the question.

An ordinary `CHANGELOG.md` entry covers it. The one thing an entry should be explicit
about is that `version` stays *present* with a different meaning rather than disappearing,
so a host grepping stubs for the release marker gets a wrong answer rather than a missing
one — but this does not warrant more than a normal entry.

### Out of scope

- A per-host opt-in to fill `version` from the host release when the source omits it.
  Not until a host asks for it.
- Any change to the stamp line itself, or to how `mask_versions` treats it.

### Verify

- `uv run pytest`, plus the three project checks (`ruff check`, `ruff format --check`,
  `pyrefly check`).
- Render the `examplehost`, `solohost`, and `multihost` fixtures and confirm: a stub whose
  source declares `metadata.version` keeps it byte for byte, a stub whose source declares
  none has no `metadata` mapping, and every stub still carries a stamp naming both
  releases.
- Bump a fixture host's version and confirm no stub reports drift; change a source's
  `metadata.version` and confirm the stub does.

### Implementation order

1. Strip the metadata keys from `stamp.py` and delete `with_metadata`; fix the
   `spec.py` docstring reference.
2. Update the tests as above, and the `stamp.py` module docstring, which currently
   documents the mirror.
3. Changelog entry, then `--force` reinstall across the known hosts.
