# Design

Why `pkgskills` exists, what it standardizes, and the decisions behind its
shape.

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
and local-only versus global-and-local modes. `pkgskills` picks one answer to
each — except the last, which turned out to be a property of the host rather
than of the machinery, and is declared per host (see Decisions).

Between them the three carried roughly 1,800 lines of delivery machinery and a
similar weight of tests, all of it hand-kept in parallel. That number alone did
not justify a package: the extraction was conditioned on a fourth host or a
second harness actually appearing, on the reasoning that three hand-kept copies
are cheaper than a library nothing new exercises, with a written contract plus a
conformance suite as the fallback if the shared code stayed thin and every host
still needed overrides. A fourth host has since adopted it, and Codex is now
the second harness, meeting both conditions.

## Decisions

**Cut line.** `pkgskills` owns the artifact layer (stamp, path by mode, drift
check, overwrite guard) and the command grammar. Host-specific work (hook
wiring, permission profiles, a drift warning inside an unrelated command)
stays in the host, reached through `after_install` and the library functions.

**Integration shape.** A library plus `register(app, host)`, which mounts the
grammar on the host's own typer app so extra host commands sit beside the
shared ones. An entry-point group (`pkgskills.hosts`) lets the standalone
`pkgskills` script check every host at once.

**One contract.** The stamp is five `pkgskills-*` keys under the frontmatter's
`metadata`, naming the host, both versions, and the mode, with a note that
`install` overwrites edits. Drift masks both
version values. It is the *only* home of that provenance. A prefix rather than a
top-level key, because the Agent Skills spec keeps extra properties in that map
and its reference validator rejects others; a prefix rather than plain keys, so
`metadata.version` still means the skill's own version, declared by the source and
passed through verbatim (see [frontmatter.md](frontmatter.md)). Anything at the path that is not a plain file this host generated is
foreign and is never replaced without `--force`. Mode is inferred from
location, never from the stamp: a stub carried to the other location reads as
drifted because its embedded commands are wrong there.

**A stamp from before adoption.** From the line alone, pkgskills cannot tell a
host's pre-adoption stamp from a pkgskills stamp that a formatter wrapped or
whose mode was corrupted, so all three read `foreign`. The host can tell, since
it wrote the old format, and `Host.legacy_stamps` lets it say so. A matching line
counts as the host's stamp through `is_stamped`, so `guard`, the stale and
previous-name removals, and the leftovers scan agree without knowing about it,
and the file reads `drifted`. That follows the policy for a current stamp: a
generated file is the tool's to rewrite, so a bare `install` does, edits included.
A pattern has to capture the mode so that a file in the wrong location reads the
same mode reason a current stamp does. Versions stay
unmasked, because a file under an old stamp is changed by definition and only
masking keeps an unchanged file `ok`. The entries live in one list in `stamp.py`,
each a pattern with its own reason. A declarative field covers this without a
pre-install hook, which would give hosts a write path ahead of the foreign check.

**The comment stamp is one of those entries.** Until the stamp moved into
frontmatter, `pkgskills` wrote it as an HTML comment, so every file installed by an
earlier release carries that line. The list holds a built-in entry for it, with its
own reason. The entry matches the whole line, so a comment that a formatter wrapped
or whose mode was corrupted stays `foreign`. It has no scheduled removal: a machine
that skipped the release dropping it would read `foreign` on every file. If it is
ever dropped, that release states the oldest version a bare `install` can upgrade
from. `stamped_by` reads the comment permanently, since a host on an older
`pkgskills` keeps writing it and a foreign reason has to name that host. A declared
pattern may not match the comment form or any line of the rendered map.

**Kinds behind an adapter.** Skills, rules, and agents each have a location
per mode and supporting harness, held in `Harness` values. `Host.harnesses`
defaults to `(CLAUDE_CODE, CODEX)` and each artifact installs in every harness
that supports its kind. Claude Code reads `.claude/skills/<name>/SKILL.md`,
`.claude/rules/<name>.md`, and `.claude/agents/<name>.md`. Codex reads skills
from `.agents/skills/<name>/SKILL.md`; its TOML agents need a different renderer,
and its `.rules` files are execution policy, so it gets no agent or prompt-rule
location. Paths are relative to `$HOME` or the repo root. Claude Code's global
skills shadow local copies, while Codex loads both, even with the same name.
Thus leftover local Codex skills are stale under a resolved global install.
Rendering stays shared: both harnesses receive byte-identical stubs.

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
reachable: the flag is refused, `pkgskills.install` refuses it, and the two checks that
only exist across two bases (a superseded local copy, a shadowed local stub) are
skipped. Distinct from the project-level mode declaration under "Not yet": that
is a per-repository setting, this is a per-host constraint.

**Anchoring.** Mode-derived locations anchor to `$HOME` or to the repository
root found by walking up to `.git` or any declared harness config directory
(`.claude` or `.codex` by default). Nothing anchors to the working directory,
which is how a local install from a
subdirectory ends up where the harness loads from. A harness directory in `$HOME`
is not a marker: `~/.claude` is the global install's own location, and treating it
as one made home the root of everything under it, where local and global paths
name the same files. `~/.git` still marks a root, so that coincidence remains
possible and has its own rule: there is one location, it is the global one, and
asking for the other is an error rather than a redirect, as it is for a mode the
host does not support. A local-only host is exempt, having no global copy to
overwrite. A host's own commands sit
outside this: `find_repo_root` is public so they can anchor the same way, and the
host guide tells them to, but nothing on `Host` or in `register` can make them. A
callback mounted by `register` could hand every command a root, at the price of
the one callback slot Typer gives an app, which a host may want for itself. The
call it would replace is one line.

**Version coupling.** A change to `pkgskills`'s rendered text would flip every
host's files to drifted with no host change. Masking both versions removes
the common case; hosts should pin a compatible range so patches flow without
host releases. A stub also has two producers now, the host and `pkgskills`;
the stamp names both versions so a bad render is attributable to one of them.

**Commands in prompts are checked, not trusted.** The reason `{cli}` exists is
that prose about a CLI goes stale, and substituting it correctly says nothing
about whether the command after it is real.
`pkgskills.testing.assert_prompt_commands` resolves every mention against the
host's own typer app, which is why it ships here rather than in each host: the
check is the same everywhere, and a host that
writes its own version writes it once per host. Two choices carry it. A mention
counts only where it is written as code — inside backticks or a fenced block —
because a body that names the bare placeholder in a sentence is talking about
the token, and reading the following words as a command path invents a command
to fail on. And the argument to `skill`, `doc`, `rule`, and `agent` is resolved
against the *declarations* rather than skipped as argument-shaped, because a
renamed doc is the stale mention most likely to happen and a scanner that stops
at the first path-shaped token never sees it.

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

- A second harness adapter: done with Codex skills; agent TOML rendering and
  prompt rules through `AGENTS.md` remain out of scope.
- A project-level declaration of expected mode and harness, so a CI check
  needs no flags.
- Reserving `<host>.md` for generated rules and steering hand-written repo
  rules to another name.
- A provenance command, in the shape of the `config` command one of the three
  hosts grew: print the resolved install state — host and `pkgskills` versions,
  harness, mode, path, stamp versions, status — with the source of each value
  tagged `flag`, `project`, `location`, or `default`. The note about a global
  copy shadowing a per-repo one becomes one row of that table rather than a
  line on stderr.
- A fingerprint test over the rendered text, so a change to what `pkgskills`
  writes cannot land without a deliberate version bump. Masking makes such a
  change cheap for hosts; it should still be a decision rather than a side
  effect.
- Recording the harness adapter's name in the stamp, so an artifact installed
  for one harness cannot pass a check against another.
- `pkgskills` shipping a skill of its own, dogfooding the pattern on the
  package that defines it.
