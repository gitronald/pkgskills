---
id: 9
slug: host-adoption-followups
status: draft
branch:
created: 2026-09-12T13:08:14-07:00
concluded:
pr:
---

# Smooth the seams a host meets after adopting the library

## Plan

A host that finishes adopting the library ends up with two kinds of command
on one CLI: the four the library mounts, and the ones the host wrote itself.
Reviewing a completed adoption turned up three seams between the two, none of
them a defect in the library, each a place where the library's behaviour and
what a host author is led to assume have drifted apart. This plan explores
each and decides, per seam, whether the fix is code, documentation, or a
deliberate "no, and here is why" written down where the next author will
find it.

The three are independent. They can land as one change or three, and the
exploration may conclude that one of them is fine as it stands.

### 1. Two notions of the repository root on one CLI

The mounted commands (`install`, `skill`, `rule`, `permissions`) resolve the
repo root with `find_repo_root`, which walks up from the working directory to
the nearest `.git` or harness config directory. That is right for them: a
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
- The `harness` argument: a host's own commands do not know the harness the
  library resolved. Document whether they should pass it (the config-directory
  fallback only fires with it) or whether `.git` alone is the right marker for
  host-side work.
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
check enforces (`"1.0.0"` passes, bare `1.0.0` reads as a number and fails),
since that is the first thing an author hits when adding the field, and it is
mentioned nowhere a host author reads.

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

### Out of scope

Any change to the stamp, the install/check flow, the pre-commit wiring, or
the `Line` mechanism. Making a host's own commands walk up is the host's
change, not this library's; this plan only decides what the library says and
offers about it.
