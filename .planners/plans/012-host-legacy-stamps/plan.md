---
id: 12
slug: host-legacy-stamps
status: active
branch: feature/host-legacy-stamps
created: 2026-10-28T09:08:00-07:00
concluded:
pr:
---

# Let a host declare its pre-adoption stamp as its own

## Plan

### Problem

A host that stamped its own generated files before it adopted pkgskills
leaves those files behind on every machine that installed an earlier
release. After the host upgrades, `classify` reports each of them `foreign`
with the reason `a <dist> stamp pkgskills did not write; hand-edited, or from
a release before <dist> adopted pkgskills`, and `install` refuses to write
until it is given `--force`.

Plan 007 kept that verdict on purpose. From the line alone, pkgskills cannot
tell three shapes apart: a stamp from before adoption, a pkgskills stamp
that a formatter line-wrapped, and one whose `mode=` token was corrupted
(`test_foreign_shapes` pins all three). The status is honest about what
pkgskills knows.

The host knows more. Its old stamp had one fixed format, which the host
wrote and can describe exactly. What it costs to leave that knowledge unused:

- Every upgraded machine needs `--force` once, and the error that asks for it
  reads like a hand edit, not an upgrade.
- A provisioning script that has to work on both fresh and upgraded machines
  ends up passing `--force` on every run. That also overwrites the files
  `foreign` exists to protect: a different dist's file, an unstamped
  hand-written one.

The policy is already inconsistent. A file under a current pkgskills stamp
whose body was hand-edited reads `drifted`, and a bare `install` rewrites it,
because the stamp said "do not edit". The same file under the host's
pre-adoption stamp, which said the same thing, is protected as `foreign`.

### Approach

**A host declares its legacy stamp.** Add an optional field to `Host`:

```python
legacy_stamps: tuple[re.Pattern[str], ...] = ()
```

Each pattern describes one stamp line the host wrote before pkgskills. It
has to match a **whole line** and capture the mode as a named group `mode`,
so a pattern that recorded no mode cannot be declared. `Host.validate`
rejects a pattern without the `mode` group, and a pattern that matches the
current `render_stamp` output for either mode (it would hide pkgskills' own
stamp).

**A declared stamp counts as generated everywhere.** `is_stamped` also accepts
a line a declared pattern matches, so every caller agrees: `guard` lets a bare
`install` through (it tests `is_generated`, not `classify`), `remove_stale_local`
and `remove_previous` can clear the file, and the leftovers scan does not report
it as hand-written. `classify` then gives it one of two `drifted` reasons:

- The recorded `mode` equals the mode being installed: reason
  `stamped by <dist> before it adopted pkgskills`. A bare `install` rewrites
  it, and `install --check` reports it with the drifted remedy.
- The recorded mode differs: today's reason,
  `rendered for mode=<recorded>, installed where mode=<mode>`. That is how a
  current stamp in the wrong mode reads, and one rule keeps this one mechanism
  when plan 010 adds pkgskills' own comment form to it.

Nothing else changes. A different dist's stamp, no stamp, and the three
same-dist shapes in `test_foreign_shapes` all stay `foreign` with today's
reasons, unless the host's own pattern matches one of them. That is the
host's declaration and the host's call.

**Edits under a legacy stamp are overwritten, and the file can be deleted.** A
bare `install` rewrites it in place, and removes it as a stale local copy or at
a previous name. This is the tradeoff, and it matches how a current stamp is
treated. Document it on the field: declare a pattern only for a stamp that also
told readers not to edit the file.

**`stamped_mode`** reads the declared patterns, so the mode reason above works.
**`mask_versions`** is not extended. A legacy file never reads `ok`: its stamp
line differs from the current render, so it is always `drifted` until rewritten.
The masking only has to stop a routine version bump from drifting an unchanged
file, and a legacy file is changed by definition.

### Relation to plan 010

Plan 010 (draft) needs the same seam for pkgskills' own cutover. When the
stamp moves into frontmatter, files carrying the current comment line should
read `drifted`, not `foreign`. That is a legacy stamp that pkgskills declares
for itself rather than one a host declares.

Build one mechanism, not two, and land this plan first: it is the smaller one,
and it can build the seam against today's stamp. The stamp module holds a single
list of entries, each a pattern with its own `drifted` reason. This plan fills
it from the host's `legacy_stamps`. Plan 010 then adds a built-in entry for the
comment form, with a reason of its own, since the reason above would be false
for a stamp pkgskills wrote. It also retargets the validation below, because its
current-stamp check cannot apply to a YAML map.

### Implementation order

1. `Host.legacy_stamps`, with validation: missing `mode` group, a pattern
   that matches the current stamp.
2. `stamp.py`: the entry list, and a lookup that returns the recorded mode and
   reason of the first matching entry, anchored per line like `_line_re`.
   `is_stamped` and `stamped_mode` consult it.
3. `classify`: the legacy reason, after the mode-mismatch reason.
4. Tests in `tests/test_install.py`:
   - A legacy line in the matching mode reads `drifted`, and a bare `install`
     passes `guard` and rewrites it to the current stamp.
   - The same line with an edited body is also rewritten.
   - A legacy line in the other mode reads `drifted` with the mode reason.
   - `remove_stale_local` and `remove_previous` clear a legacy file, and the
     leftovers scan does not report it.
   - A host that declares nothing keeps every `test_foreign_shapes` row
     unchanged.
   - Validation rejects each bad pattern.
5. Docs: the `Host` docstring entry, a paragraph in `docs/design.md` beside
   the status vocabulary, and a README note that a host migrating from its
   own stamps can declare them. `CHANGELOG.md` under `[Unreleased]`, Added:
   the field is optional, so no host changes behavior until it declares one.

### Risks

- **A loose pattern** turns a hand-written file into one a bare `install`
  overwrites or deletes. The whole-line anchor and the validation narrow this; the
  docstring says to match the old stamp exactly, version token included as
  `\S+`.
- **A pattern that outlives its use.** A host can drop its declaration once
  no supported upgrade path starts from a pre-adoption release. Say so in the
  docs; pkgskills has no way to know when.

### Out of scope

- Recognizing an older render by its content (hashing past releases'
  output).
- Changing how a different dist's stamp is treated.
- A pre-install hook that lets a host rewrite files before `guard` runs. The
  declarative field covers the case without giving hosts a write path ahead
  of the foreign check.

## Log

- **2026-10-31T15:53:19-07:00** — Compared this plan with plan 010 against the code and settled where they disagreed; the Plan section now reflects each decision.
  - A recognized legacy stamp counts as generated everywhere. As first written, `guard` would still have refused a bare `install`, because it tests `is_generated` rather than `classify`.
  - A mode mismatch reads `drifted` with the existing mode reason, not `foreign`.
  - This plan lands before plan 010. Each list entry carries its own reason, and plan 010 adds the comment form.
- **2026-10-31T16:04:07-07:00** — Activated.
  - Branch: `feature/host-legacy-stamps`
  - Base: `dev` at `8272974`
  - Worktree: `.worktrees/012-host-legacy-stamps`
  - PR: pending
