---
id: 0
slug: multi-skill-hosts
status: draft
branch:
created: 2026-09-04T19:53:42-07:00
concluded:
pr:
---

# Support hosts with several single-source skills and print-only docs

## Plan

### Context

Declaring a fourth host against `mli` 0.1.0a0 surfaced the gaps below. The host is shaped
unlike the three the design was drawn from: it ships **several single-source skills** (one
trigger each, no dispatcher), each body **points at sidecar reference documents** that load
only when a step needs them, every body uses `{cli}`, and the host is **bound to one
repository**, so global mode is meaningless for it. None of the three fixture-derived shapes
(one dispatcher, one solo skill) exercise that combination, which is why the two defects in
Part 1 sit behind passing tests.

Reviewed 2026-09-09 against that host's now-written adoption plan and against plans 001 and
002, which landed in the meantime. Every part below still holds — none of the four code parts
has been implemented — and the review's changes are recorded inline: a note on the fixture in
Part 1, sequencing in Part 2, a named consumer in Part 3, a widened scanner in Part 4, a git-pin
stopgap and a scrub gate in Part 5, and a reordered Order. Plans 001 and 002 do not conflict,
but Part 3 now has more surface to touch: 002 made a stale local copy a gating status, so
skipping `remove_stale_local` and `shadowed_skills` for a local-only host has to fit that.

### Part 1: two defects in multi-skill hosts

**The stub names a command that fails.** `render_stub` renders the load instruction for a
non-dispatching skill as `host.skill_command(mode)`, which is `<cli> skill` with no name. The
`skill` command then refuses to print when the host ships more than one body
(`"ships N skill bodies; name one of: ..."`, exit 1). So in a host with two or more
single-source skills, every generated stub tells the model to run a command that exits 1.
`test_single_skill_stub_names_mode_correct_commands` asserts the nameless form, so the suite
enforces the defect.

- Fix: render `host.skill_command(mode, <printable name>)` for every non-dispatching skill.
  Naming the body is harmless on a solo host, so there is no special case.
- Test: a third fixture host, `multihost`, with two single-source skills and no dispatcher;
  assert each stub carries `<cli> skill <name>` and that running the printed command through
  `CliRunner` succeeds. Update the solo-host assertion to the named form.

The fixture has to carry the second defect deliberately. The host that surfaced these lays
its bodies out as `skills/<skill>.md`, so every stem already equals its skill name and only
the first defect bites there — a fixture modelled on it would leave the keying fix unproven.
`multihost` names one source file differently from its skill for exactly that reason.

**Bodies are keyed by file stem, not skill name.** `Host.skill_sources()` keys every body by
the source file's stem. For a dispatcher that is right: the stems are the subcommands. For a
single-source skill the model knows the skill by its `name` (it is in the stub's frontmatter
and in the slash command), and `<cli> skill <name>` fails whenever the file is not named
after the skill. `skill --list` has the same problem: it prints stems where a user expects
skill names.

- Fix: `skill_sources()` keys a single-source skill by `skill.name` and a dispatcher's
  sources by stem, rejects a collision between the two namespaces in `Host.validate`, and
  `skill --list` prints those keys. `stub_frontmatter` already checks that the source's
  frontmatter `name` equals `skill.name`, so the three agree.
- Test: in `multihost`, name one source file differently from its skill and assert
  `skill <skill.name>` prints it.

### Part 2: a print-only `Doc` kind

A skill body that says "read `references/x.md` before running" has no way to do that once
the body is printed from a package: there is no skill directory next to the stub. The host
had to add its own `doc`-style command (another host's print commands are the same
workaround), and to do it correctly it needed `installed_mode`, which `mli` does not export,
to render `{cli}` the way `skill` does.

Add a fourth declared thing, `Doc`, that is printed and never installed:

```python
Doc(name="tidy/fields", source="references/tidy/fields.md", render_cli=True)
```

- Docs live on the host as `Host.docs`, not in `artifacts`: an artifact in `mli` is something
  materialized on disk with a location per mode, and a doc has neither. `Host.validate` checks
  name uniqueness among docs and that each source exists, and leaves the harness out of it.
- `register` mounts `<cli> doc <name>` (and `doc --list`) when the host declares any. Printing
  goes through `render_prompt` with the same mode-resolved `{cli}` substitution `skill` uses.
  Names may contain `/` so a host can namespace docs by the skill that owns them; the
  namespace is a convention, not a rule.
- `install`, `check`, and `mli check` ignore docs entirely; the wheel is the only place they
  have to exist, and `mli.testing.wheel_files` already covers that.
- README: a "Documents" section, and a line in "Declare a host" saying a body must not
  reference files by a path relative to the stub, because after `install` there is nothing
  there; use a `Doc` and `{cli} doc <name>`.
- Export `installed_mode` (or a `printing_mode(host, root)` wrapper) from the package so a
  host that still wants a print command of its own renders `{cli}` consistently.

**Sequencing.** This part is worth most before the adopting host rewrites its skill bodies,
not after. That host is shipping its own print command and rewriting every body to name it;
once those bodies are written, adopting `Doc` is a second rewrite of all of them plus a
command rename. If Part 2 cannot land first, weigh letting the host choose the command's
name rather than hardcoding `doc`, so adoption is a declaration change instead of a
body-wide substitution.

### Part 3: a local-only host

A host whose skills only make sense inside one repository has no use for global mode, and
a stray `<cli> install` (no `--local`) writes stubs under `$HOME` that then shadow the
per-repo ones for that repository. Today the host has to document "always pass `--local`".

- `Host.modes: tuple[Mode, ...] = ("global", "local")`. A host declares `modes=("local",)`.
- With a single mode, `install` and `install --check` use it without a flag; passing the
  other mode's flag is an error naming the host's modes. `installed_mode`'s fallback becomes
  the host's first mode instead of the literal `"global"`, so `skill` and `doc` render `{cli}`
  for the right mode before the first install.
- The stub's check and repair commands already follow the mode they were rendered for, so
  nothing changes there. `remove_stale_local` and `shadowed_skills` are skipped for a host
  that has no global mode.
- Tests: `multihost` declares `modes=("local",)`; assert the flagless install lands in the
  repo, that `install --check` reports against the local path only, and that the global
  path is never touched.

This is distinct from the design doc's "project-level declaration of expected mode": that is
a per-repository setting for CI; this is a per-host constraint.

This is the cheapest part with a consumer already waiting on it: the adopting host's plan
leaves open whether to document always passing `--local` or to ask `mli` for a per-host
flag, which this closes.

### Part 4: a "commands in prompts are real" test helper

The reason the pattern exists is that prose about a CLI goes stale. `mli` renders `{cli}`
but nothing checks that what follows it is a command the host actually has. The adopting
host has this check in its own plan rather than in code, with a note that it could move into
`mli.testing` if it proves useful — so this is a chance to ship it once, upstream, before it
is written host-side at all.

- `mli.testing.prompt_commands(host) -> list[PromptCommand]`: scan every skill body, doc,
  rule, and agent the host ships for `{cli} <tokens>` and yield the source, line, and token
  list up to the first token that looks like an argument (`<...>`, a path, an option).
- `mli.testing.assert_prompt_commands(host, app)`: resolve each token path against the
  typer app (`typer.main.get_command(app)`, walking `commands` on each click group) and fail
  with the source and line of every mention that does not reach a real command. The
  shared grammar's own commands (`skill`, `doc`, `rule`, `agent`, `install`) resolve like
  any other.
- A token that names a declared thing is not an argument to stop at. `{cli} doc
  tidy/fields` and `{cli} skill <name>` are the mentions most likely to go stale, and a
  scanner that stops at the first path-shaped token never checks either. So resolve the
  argument to `doc`, `skill`, `rule`, and `agent` against the host's declarations, and fail
  the same way when it names nothing declared. The adopting host's own version of this check
  validates exactly those forms; a helper that skips them would not replace it.
- Tests: `examplehost` bodies mention `{cli} validate` (real) and gain one deliberate
  `{cli} nonexistent` in a doc fixture used only by the negative test.

### Part 5: make the package installable

No host can `uv add mli` today: the repository has no remote and nothing is released.

- Push the repository and run `stanza init`; release `0.1.0a1` to PyPI (the name was free on
  2026-09-04) so hosts pin `mli>=0.1.0a1,<0.2` per the design doc's version-coupling note.
- **A git pin is an accepted stopgap.** The first adopting host takes either the released
  alpha or a git dependency pinned at a commit, so the push alone unblocks it and the release
  can follow. Do the push first for that reason: it is the whole prerequisite, and it costs
  no version decision.
- **Scrub before the fold, not just before the push.** `notes.md` and `plan.md` are untracked
  working notes (gitignored), so nothing in them reaches a push as they stand — but they name
  a private consumer repo and a sibling data repo, and folding what is still useful into
  `docs/design.md` moves that text into a tracked file in a repo meant to be public. Generalize
  those names as part of the fold (see the no-local-specifics convention), and grep the tracked
  tree for them before pushing. Tracked files are clean today: they name only the sibling tool
  packages, which are the pattern's own lineage. Their ignore patterns were bare filenames,
  which match at every depth and silently ignored `.planners/plans/*/plan.md` as well; they are
  now anchored to the root (`/plan.md`).
  **Scrub done 2026-09-09.** The survey note held nothing the design doc did not already state in
  public-safe form, so it was retired unabsorbed. From the proposal, four things had no other
  home and moved into `docs/design.md`: the cost and exit criterion the extraction was
  conditioned on, the two-hosts-before-an-option rule, the two-producers note under version
  coupling, and four open items appended to "Not yet" (a provenance command, a render
  fingerprint test, the harness name in the stamp, and `mli` dogfooding a skill of its own).
  Everything named in the fold is generalized; both files are archived out of the tree.
- Add a "Drift gate" snippet to the README: a local pre-commit hook running
  `<cli> install --local --check` with `pass_filenames: false`, scoped to the host's prompt
  package and the harness config directory. Hosts keep asking for this and it needs no code.

### Smaller items

- `Host.render_cli: bool = False` as a default for artifacts and docs that leave their own
  `render_cli` unset. A host whose every body uses `{cli}` currently repeats the flag on each
  declaration — the first adopting host writes `render_cli=True` on every skill and rule it
  declares, because every body it ships carries the token.
- `skill --list` on a solo host prints the stem, which may differ from the skill's name;
  Part 1's keying fixes it for free.

### Order

Reordered after reading the first adopting host's plan. Part 5 moves to the front: that host
cannot resolve `mli` as a dependency at all, so nothing else here reaches it, and a git pin
at a pushed commit satisfies it without a release. Part 3 moves ahead of Part 2 because it
closes an open question in that plan for very little code, while Part 2's window is tied to
when the host's bodies get rewritten.

1. Part 5's push, so the host can pin `mli` at a commit and start. The release follows.
2. Part 1 with the `multihost` fixture (a bug fix; ship as `0.1.0a1`).
3. Part 3, then Part 2, then Part 4, each its own PR and alpha.
4. Smaller items ride along with whichever part touches the same code.

### Out of scope

- A second harness adapter.
- The project-level `[tool.mli]` mode declaration from the design doc's "Not yet" list.
- Porting the three original hosts; their order is
  unchanged and each benefits from Part 1 only if it ever ships a second single-source skill.
