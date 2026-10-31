---
id: 9
slug: host-adoption-followups
status: implemented
branch: feature/host-adoption-followups
created: 2026-09-12T13:08:14-07:00
concluded:
pr: https://github.com/gitronald/pkgskills/pull/25
---

# Smooth the seams a host meets after adopting the library

## Plan

A host that finishes adopting the library ends up with two kinds of command
on one CLI: the ones the library mounts, and the ones the host wrote itself.
Reviewing a completed adoption turned up three seams between the two, none of
them a defect in the library, each a place where the library's behaviour and
what a host author is led to assume have drifted apart. This plan explores
each and decides, per seam, whether the fix is code, documentation, or a
deliberate "no, and here is why" written down where the next author will
find it.

The three are independent. They can land as one change or three, and the
exploration may conclude that one of them is fine as it stands.

### 1. Two notions of the repository root on one CLI

The mounted commands (`skill`, `install`, and, when declared, `doc`, `rule`,
`agent`, `permissions`) resolve the repo root with `find_repo_root`, which walks
up from the working directory to the nearest `.git` or harness config directory.
That is right for them: a
local install has to land where the harness loads from, not in whatever
subdirectory the command ran in (`docs/design.md` says so).

A host's own commands do not inherit that. A host that reaches for
`Path.cwd()` in its lifecycle commands, which is the obvious default and is
what a host migrating from a home-grown install layer already had, now ships
a CLI whose command families disagree from any subdirectory: the library's
half writes at the true root, the host's half writes under the subdirectory.
Before adoption the host at least disagreed with itself consistently.

The function is already public and exported, so the mechanics need nothing.
Questions to settle:

- Is this a documentation gap, a code gap, or both? The README's host guide
  never says "your own commands should resolve the root the same way", and
  there is no place in the `Host` declaration or the `register` call where the
  library could enforce it. A sentence in the host guide and in the `register`
  docstring may be the whole change.
- Should `register` (or a helper next to it) hand hosts a ready `root` — e.g.
  a typer callback or dependency that resolves it once for every command on
  the app — so the shared notion is something a host opts into rather than
  something it has to remember? Weigh that against the library's stance of
  staying out of the host's command grammar.
- The `harnesses` argument: a host's own commands do not pass the harnesses the
  library walks with unless told to. Document whether they should pass them (the
  config-directory fallback only fires with them) or whether `.git` alone is the
  right marker for host-side work.
- Confirm the "falls back to `start` itself" case is what a host wants when no
  marker exists, since a host command may prefer to refuse rather than write
  into an arbitrary directory.

### 2. A `metadata.version` on a dispatcher source goes nowhere

The spec-conformance check accepts a `metadata` block on each skill source,
and the Agent Skills spec makes `version` a natural key to put there. A
host that adds `metadata.version` to the sources behind a dispatcher will find
the installed stub carries no `metadata` at all: `stub_frontmatter` lifts the
block only for a single-source skill, and a dispatcher generates its own
frontmatter with no source to take a version from. The docstring states this
plainly; the host guide and the layout doc do not, so an author finds out by
diffing the stub after install and noticing nothing changed.

Nothing is broken, and the field is not wasted in principle: it is the
source's own version, and a linter or a future reader can use it. But the
library should take a position rather than leave the host to discover the
asymmetry. Options, in rough order of preference:

- **Document it.** Say in the layout doc and the host guide that a
  dispatcher stub declares no `metadata`, that a source's `metadata` is the
  source's own, and what a host gains (or does not) by setting it.
- **Surface it.** A dispatcher could carry a derived field — the host's
  distribution version is already in the stamp line, so the question is
  whether a `metadata.version` on the stub adds information or just repeats
  it. Lifting per-source versions into the stub body (one per subcommand in
  the listing) is another shape; decide whether a harness or a person would
  ever read it there.
- **Check it.** If the answer is "hosts should not bother", the conformance
  check could note a `metadata.version` on a dispatcher source as
  informational, the way `entry-file` is a rule slug rather than an error.
  Probably too loud; record the reasoning if rejected.

Whatever the decision, the plan should also settle the quoting rule the spec
check enforces (a bare `1.0` or `1` reads as a number and fails, a bare date
reads as a timestamp and fails, and a bare `1.0.0` reads as a string and passes),
since that is the first thing an author hits when adding the field. The docs
state the rule for `1.0` and do not say that `1.0.0` passes.

### 3. The layout doc says flat sources are fine; the test helper fails them

`docs/source-layout.md` has a section titled "Flat sources still work": a
host that ships `skills/<name>.md` keeps working, may mix layouts, and pays
only in "spec conformance of the source tree itself, which matters when a
linter is pointed at the package". `check_layout` agrees, describing the
flat case as "a departure from the spec but not an error pkgskills raises
on", with a rule slug so a caller decides how loudly to say so.

`assert_spec_conformant`, the helper the host guide tells every host to put
in its test suite, raises on any violation, `entry-file` included. So a host
that reads the layout doc, keeps a flat layout because its sources are
dispatcher bodies never installed as skills of their own, and then follows
the testing section, gets a failing suite whose fix is to move every file.
Both documents are individually correct; together they send a host author in
a circle, and the resolution the host reaches (move the files) is fine but
was avoidable planning.

Decide which of these the library means:

- **The layout is required for a tested host.** Then say so in the layout
  doc's flat-sources section: flat sources keep *working*, but a host that
  adopts `assert_spec_conformant` must use the directory layout, and a
  dispatcher's sources are no exception. Say it in the host guide's testing
  section too, next to the helper.
- **Flat is a legitimate choice a host can keep.** Then the helper needs a
  way to exclude a rule (`ignore=("entry-file",)` or similar) so the host
  can assert everything else and record the one exception in its own test,
  and the layout doc should show that call.
- **Both, by role.** A dispatcher's sources are read by the library and never
  installed as skills, so the spec's per-skill layout rules arguably do not
  apply to them at all; a single-source skill's source is installed as a
  skill and must conform. If that distinction holds, `check_host` could scope
  `entry-file` to sources that become skills, and the flat-sources section
  would explain the rule by role rather than by tolerance.

The third option is the most principled and the most work; the first is a
paragraph. Whichever wins, the two documents and the helper must end up
saying the same thing.

### Decisions

Settled at review, against the code as it stands. No seam needs new public API;
each fix is documentation, plus tests that keep the documentation true.

1. **Seam 1 is documentation.** Hosts are told to resolve their root with
   `find_repo_root(harnesses=HOST.harnesses)`, in the README's host guide, the
   `register` docstring, and the design doc's Anchoring decision.
   - No callback or dependency from `register`. Typer gives an app one callback,
     so one mounted by the library would collide with a host's own
     `@app.callback()`, and the call is one line. A helper or option for this is
     also held back by "Two hosts before an option" in `docs/design.md`.
   - Pass `harnesses`. It is the only form that agrees with the mounted commands
     in every tree: without it, a nested directory holding `.claude/` or `.codex/`
     is a root to the library and not to the host.
   - The fallback stays as it is. A host command that must refuse outside a
     repository looks for `.git` at the result and above it. Testing the result
     alone would refuse inside a repository whose subdirectory holds `.claude/`.
     The check also covers the case the walk's docstring does not mention: under
     a home directory holding `.claude/`, the walk stops at `$HOME` rather than
     falling back to `start`.
2. **Seam 2 is documentation.**
   - Document it: a dispatcher stub declares no `metadata`, and a dispatcher
     source's `metadata` is the source's own, read by a linter or a person and
     never lifted. The stub does not carry a `metadata.version` for the host's
     release either, since the stamp already records it.
   - Surfacing per-source versions belongs to plan 010, whose subcommand table
     has a Version column. When 010 lands, it revises the sentence this plan
     writes.
   - Rejected: an informational check on a dispatcher source's `metadata.version`.
     The value is legitimate for a linter and harmless to the stub, so a note
     would flag correct sources in every host that versions them.
   - Quoting: the rule is to quote every version. A bare `1.0.0` passes today, and
     the docs say so, because an author who sees it pass will otherwise doubt the
     rule. Quoting stays the advice since the same key turns into a float the day
     it reads `2.0`.
   - Add the test the review found missing: a dispatcher whose sources declare
     `metadata`, with none of it in the stub.
3. **Seam 3 takes the first option, and names the existing route out.**
   `assert_spec_conformant` means the whole spec, so a host that adopts it uses the
   directory layout, dispatcher sources included. The layout doc and the testing
   section both say so.
   - A host that keeps flat sources on purpose filters the report it already has:
     `Host.check_spec()` returns `Violation`s with stable `rule` slugs. Both docs
     show that call and a test pins it, so `ignore=` adds nothing and is held back
     by "Two hosts before an option".
   - Rejected: scoping `entry-file` by role. Its premise is that a single-source
     skill's source is installed as a skill, but what installs is the stub, at a
     path built from `Skill.name`. Only the source's frontmatter travels, and a
     flat single-source file installs a fully conformant skill, which is exactly
     what the docs promise for `skills/audit-body.md`. So the layout rule applies
     to neither role at install time, and matters to both only when a linter reads
     the package.
   - `check_layout`'s docstring is corrected to say which surfaces raise on a flat
     source, so all three agree.

### Out of scope

Any change to the stamp, the install/check flow, the pre-commit wiring, or
the `Line` mechanism. Making a host's own commands walk up is the host's
change, not this library's; this plan only decides what the library says and
offers about it.

## Log

- **2026-10-31T12:31:37-07:00** — Review: narrowed. All three seams are still open in the code and docs at 421e9f2, with one part of seam 2 already done and several facts in the spec out of date.
  - Already done: the quoting rule. `docs/frontmatter.md`, `docs/source-layout.md`, and the README's testing section all state it, so "mentioned nowhere a host author reads" no longer holds. Remaining scope for seam 2: say that a dispatcher source's `metadata` never reaches the stub.
  - Wrong in the spec: bare `1.0.0` does not read as a number. `yaml.safe_load` returns the string `1.0.0`, so it passes; `1.0`, `1`, and a bare date are what fail.
  - Stale in the spec: `find_repo_root` takes `harnesses`, a sequence, since 6b8085d, and `register` mounts up to six commands (`skill`, `install`, and, when declared, `doc`, `rule`, `agent`, `permissions`).
  - Overlap: draft plan 010 proposes a Version column in the dispatcher's subcommand table, which is this plan's "surface it" option. 010 owns that option.
  - Evidence gap: `test_dispatcher_stub_declares_no_metadata` uses `examplehost`, whose dispatcher sources declare no `metadata`, so the test cannot fail for the behaviour seam 2 describes.
  - New finding: `find_repo_root` with harnesses stops at `$HOME` when `~/.claude` exists, so from a directory under home with no repository it returns home, not `start`. Checked by running it against a temporary tree.
- **2026-10-31T12:32:07-07:00** — Activated.
  - Branch: `feature/host-adoption-followups`
  - Base: `dev` at `a1023e8`
  - Worktree: `.worktrees/009-host-adoption-followups`
  - PR: pending
- **2026-10-31T12:34:00-07:00** — PR opened: https://github.com/gitronald/pkgskills/pull/25
- **2026-10-31T12:35:02-07:00** — Implemented: 3 commits ahead of `dev`.
