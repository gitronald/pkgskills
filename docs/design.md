# Design

Why `mli` exists, what it standardizes, and the decisions behind its shape.

## The pattern it extracts

Three packages ([planners](https://github.com/gitronald/planners),
[citefinder](https://github.com/gitronald/citefinder), and
a third host package) arrived at the same
delivery model for their Claude Code skills, each implementing it by hand:

1. The package is the source of truth. Prompt bodies ship as package data, so
   a package upgrade updates the instructions with no install step.
2. `<cli> skill [<name>]` prints a body on demand.
3. `<cli> install` writes a generated, version-stamped stub carrying only the
   frontmatter the harness reads off disk, plus the instruction to run
   `<cli> skill <name>`.
4. `<cli> install --check` reports drift and exits non-zero unless ok.
5. The stub tells the agent to check before dispatching and to start a fresh
   context after regenerating.

The pattern began in the third package, was generalized by planners (install modes,
the `{cli}` placeholder, rules, a pre-commit hook), and was trimmed back to a
single body by citefinder. Their implementations agreed on the shape and
disagreed on details: an HTML-comment stamp versus a frontmatter `version:`
key, masked versus byte-for-byte drift, refuse-foreign versus skip-existing,
and local-only versus global-and-local modes. `mli` picks one answer to each —
except the last, which turned out to be a property of the host rather than of
the machinery, and is declared per host (see Decisions).

Between them the three carried roughly 1,800 lines of delivery machinery and a
similar weight of tests, all of it hand-kept in parallel. That number alone did
not justify a package: the extraction was conditioned on a fourth host or a
second harness actually appearing, on the reasoning that three hand-kept copies
are cheaper than a library nothing new exercises, with a written contract plus a
conformance suite as the fallback if the shared code stayed thin and every host
still needed overrides. A fourth host has since adopted it, which is the
condition being met.

## Decisions

**Cut line.** `mli` owns the artifact layer (stamp, path by mode, drift
check, overwrite guard) and the command grammar. Host-specific work (hook
wiring, permission profiles, a drift warning inside an unrelated command)
stays in the host, reached through `after_install` and the library functions.

**Integration shape.** A library plus `register(app, host)`, which mounts the
grammar on the host's own typer app so extra host commands sit beside the
shared ones. An entry-point group (`mli.hosts`) lets the standalone `mli`
script check every host at once.

**One contract.** The stamp is an HTML comment after the frontmatter naming
both versions, the mode, and the repair command. Drift masks every version
token. The frontmatter `version:` key the other implementations used is not
an alternative to it but a mirror of it: a skill stub declares both versions
under `metadata` as the Agent Skills spec defines, while the stamp stays the
thing `--check` matches on and the only mechanism rules and agents have
(see [frontmatter.md](frontmatter.md)). Anything at the path that is not a plain file this host generated is
foreign and is never replaced without `--force`. Mode is inferred from
location, never from the stamp: a stub carried to the other location reads as
drifted because its embedded commands are wrong there.

**Kinds behind an adapter.** Skills, rules, and agents each have a location
per mode, held in one `Harness` value. Claude Code is the only adapter until
a second harness is actually in use; the seam exists so that landing one is a
new value, not a redesign.

**Stubs versus copies.** A skill is a stub because the harness loads it and a
model then runs the CLI. A rule or agent is a copy because the harness reads
its full text with no model in the loop. The two share the stamp and the
check; only the render differs.

**Documents, which are neither.** Print-on-demand takes the skill directory
away, and with it every sidecar a body used to reach by relative path. A `Doc`
gives that sidecar a command instead — `<cli> doc <name>` — and nothing else:
it is never written, stamped, or checked, so it lives on `Host.docs` rather
than in `Host.artifacts`, where everything has a location per mode. The
alternative, a fourth `Kind`, would have put a thing with no path through code
whose whole subject is paths. Two hosts had already grown a print command of
their own for exactly this — one of the three originals, with two such commands,
and the fourth — which is what made it a declaration rather than an option (see
"Two hosts before an option"); the same
reasoning exports `printing_mode`, since a host that keeps its own command must
resolve `{cli}` the way `skill` does or print commands that do not run.

**Modes a host opts out of.** Both modes are first-class, but which of them a
given host has any use for is the host's to declare: `Host.modes` lists them in
preference order, and the first is what a flagless `install` and a pre-install
render use. This is the one place the three originals disagreed that could not
be settled by picking a side — local-only and global-and-local are both correct,
for different hosts — so it is a declaration rather than an answer. A host bound
to one repository declares `modes=("local",)`, and the other mode stops being
reachable: the flag is refused, `mli.install` refuses it, and the two checks that
only exist across two bases (a superseded local copy, a shadowed local stub) are
skipped. Distinct from the project-level mode declaration under "Not yet": that
is a per-repository setting, this is a per-host constraint.

**Anchoring.** Mode-derived locations anchor to `$HOME` or to the repository
root found by walking up to `.git` or the harness config directory. Nothing
anchors to the working directory, which is how a local install from a
subdirectory ends up where the harness loads from.

**Version coupling.** A change to `mli`'s rendered text would flip every
host's files to drifted with no host change. Masking both versions removes
the common case; hosts should pin a compatible range so patches flow without
host releases. A stub also has two producers now, the host and `mli`; the stamp
names both versions so a bad render is attributable to one of them.

**Two hosts before an option.** Some of the divergences the three hosts had were
deliberate and some were accidents, and the difference is not visible from one
host's side. So a behavior difference is a per-artifact or per-host declaration
only once a second host needs it — never a per-host code path, and never an
option added on the strength of a single caller.

## What was borrowed from where

- planners: the generated-artifact abstraction, mode as one resolved value,
  the `{cli}` substitution, removing a stale local copy after a global
  install, the shadowing note.
- citefinder: repository-root discovery, symlink handling, the non-UTF-8
  stdout fallback, version masking, the wheel-build test, and the argument
  that print-on-demand is worth having for a single body.
- The third package: the dispatcher holder generated from each body's frontmatter,
  and subagent definitions as an installed kind.

## Malformed shapes

Enumerated rather than discovered: a directory at the path, a dangling or
live symlink, undecodable bytes, an unstamped file, another package's stamp,
and a copy rendered for the other mode. Each has a status and a reason the
CLI prints, and each has a test.

## Not yet

- A second harness adapter.
- A project-level declaration of expected mode and harness, so a CI check
  needs no flags.
- Reserving `<host>.md` for generated rules and steering hand-written repo
  rules to another name.
- A provenance command, in the shape of the `config` command one of the three
  hosts grew: print the resolved install state — host and `mli` versions,
  harness, mode, path, stamp versions, status — with the source of each value
  tagged `flag`, `project`, `location`, or `default`. The note about a global
  copy shadowing a per-repo one becomes one row of that table rather than a
  line on stderr.
- A fingerprint test over the rendered text, so a change to what `mli` writes
  cannot land without a deliberate version bump. Masking makes such a change
  cheap for hosts; it should still be a decision rather than a side effect.
- Recording the harness adapter's name in the stamp, so an artifact installed
  for one harness cannot pass a check against another.
- `mli` shipping a skill of its own, dogfooding the pattern on the package that
  defines it.
