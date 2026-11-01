---
id: 12
slug: host-legacy-stamps
status: done
branch: feature/host-legacy-stamps
created: 2026-10-28T09:08:00-07:00
concluded: 2026-10-31T16:12:23-07:00
pr: https://github.com/gitronald/pkgskills/pull/27
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
- **2026-10-31T16:07:19-07:00** — PR opened: https://github.com/gitronald/pkgskills/pull/27
- **2026-10-31T16:08:54-07:00** — Implemented as specified, with these calls the Plan left open.
  - Whole-line matching uses `fullmatch` on each line from `splitlines`, so a pattern needs no anchors of its own.
  - A `mode` group that captures anything but `global` or `local`, or stays unset, is no match. The file then stays `foreign`.
  - A file carrying a current stamp is never a legacy one, even when its body quotes a declared line.
  - The current-stamp check imports `render_stamp` inside `Host`, because `stamp` imports `host`. Only a host that declares a pattern pays for the render at construction.
  - Tests went where their subject already lives, not all in `tests/test_install.py`: validation in `test_host.py`, the lookup in `test_render.py`, and an added end-to-end upgrade in `test_cli.py`.
  - For plan 010: `_line_re` has no end anchor, so a line that begins with the current form reads as a current stamp however it ends, and a legacy pattern never sees it.
- **2026-10-31T16:08:59-07:00** — Implemented: 5 commits ahead of `dev`.
- **2026-10-31T16:23:33-07:00** — Added `Host.legacy_stamps` with validation, the legacy entry list and lookup in `stamp.py`, the `classify` reason, tests, and docs.
  - Review follow-up: a `medium` review raised 6 candidates and confirmed 2. Reviewed and approved for merge by the owner.
  - Actioned: the lookup split lines with `splitlines`, so a declared stamp followed by a form feed or U+2028 and prose read as generated. It now splits on newlines only, with regression cases in `test_a_legacy_pattern_has_to_match_a_whole_line`.
  - Actioned: a test comment claimed anchored patterns were covered. The test now runs one, and also covers CRLF endings.
  - Conscious no-ops: the three scans `classify` makes of a legacy file, measured at about 1.2 ms over 40 files; `_as_mode` and the per-call entry tuple, which are shape only, with no failure behind them.
  - Checks at the review fix: ruff check, ruff format, pyrefly, and pytest pass locally (406 tests); CI's test job passes on Python 3.11 through 3.14.

## Retrospective

- Routing the lookup through `is_stamped` kept the change small, as the plan predicted: `guard`, both removals, and the leftovers scan needed no edits and agree by construction.
- The one real defect was in the destructive direction and came from an unconsidered default. "Whole line" was specified, and `splitlines` quietly meant something wider than the `(?m)^` rule beside it. When a check guards an overwrite, compare its line rule with the one it sits next to.
- The Plan said a whole-line match but left open what a loose `mode` capture does. Treating a non-mode token as no match keeps a corrupted file `foreign`, which is the safe side for a field that lets `install` delete files.
- `_line_re` has no end anchor, which surfaced only when a test fixture read as a current stamp. It limits what a legacy pattern can claim, and plan 010 replaces that matching, so it is noted for that plan in this Log rather than changed here.
- The list with a per-entry reason has one source so far, so it looks heavier than this plan needs. It is the seam plan 010 fills, and it was kept for that reason.
