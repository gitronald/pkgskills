---
id: 8
slug: host-install-machinery
status: done
branch: feature/host-install-machinery
created: 2026-09-11T19:38:49-07:00
concluded: 2026-09-11T20:46:39-07:00
pr: https://github.com/gitronald/pkgskills/pull/8
---

# Move hook wiring, in-place line artifacts, and superseded paths upstream

## Plan

After plan 007, the first adopting host (`planners`) still keeps roughly 450
lines of install machinery behind `after_install` and `extra_checks`. Reviewing
that remainder, most of it is mechanism any host with the same needs would
rewrite: wiring a pre-commit hook, owning one line of a file the host does not
own, and cleaning up an artifact's previous path. Only the hook entries, the
line, and the old name are host data. This plan moves the mechanism up, in
three independent pieces, in the order a host is most likely to want them.

The library's own posture does not change: it still runs no subprocess on its
own initiative. Every shell-out below happens inside a host's `after_install`
or `extra_checks`, through `pkgskills.proc.run`, because the host asked for it.

### 1. Pre-commit hook wiring — `pkgskills.precommit`

A host that ships a `validate` (or `index`) command wants it to run as a git
hook, and today has to write all of this itself:

- append a `- repo: local` block naming its hooks to
  `.pre-commit-config.yaml`, creating the file when absent, and re-sync the
  `entry` line when the install mode changes (`<cli>` versus `uv run <cli>`);
- run `pre-commit install` for each hook type the block uses (`pre-commit`,
  `post-merge`, …);
- tell whether the hook is *registered in this clone*, honoring
  `core.hooksPath`, since a config that names the hook says nothing about
  whether git will run it;
- optionally add `pre-commit` as a dev dependency so the first install is
  one step;
- report all of that as `install --check` rows without gating on it — a
  correct consumer may legitimately not have the hook registered, which is
  exactly why `ExtraCheck.gates` exists.

Add a module with a small declaration and two entry points:

```python
@dataclass(frozen=True)
class Hook:
    id: str            # "planners-validate"
    stage: str         # "pre-commit" | "post-merge" | ...
    args: tuple[str, ...] = ()   # appended after the host invocation
    name: str | None = None
    pass_filenames: bool = False
    always_run: bool = False
    files: str | None = None

def wire(report: InstallReport, hooks: Sequence[Hook], *, activate: bool = True) -> HookReport
def checks(host: Host, root: Path, mode: Mode | None, hooks: Sequence[Hook]) -> list[ExtraCheck]
```

`wire` derives the `entry` from `host.invocation(report.mode)` plus the hook's
`args`, so the mode-correctness rule is enforced rather than remembered. It
appends only what is missing, re-syncs an entry that names the other mode,
leaves an entry that is deliberately different alone (a dev repo that keeps
`uv run <cli>` because the host is a local dependency), and registers each
distinct stage. `checks` returns one row per hook: `active`, `unregistered`,
`missing` (not in the config), or `not a git repo`, each with `gates=False`
and a note naming the command that fixes it.

`HookReport` is the write-time vocabulary and stays separate from the check
rows, per the rule on `ExtraCheck`.

What stays host-side is the tuple of `Hook` declarations and the two calls.
The dev-dependency step (`uv add --dev pre-commit`) is offered as a separate
function, not folded into `wire`, so a host decides whether to touch
`pyproject.toml`.

### 2. An in-place line artifact — `Line`

Some generated files need one line in a file the host does not own; the
motivating case is `<index path> merge=union` in `.gitattributes`, so a
generated index resolves on merge instead of conflicting. Today the host
re-implements the whole read/classify/write loop for that one line, with a
fourth status the library's `Status` deliberately lacks.

`classify`'s docstring already reserves the answer: an artifact edited in
place needs its own `unreadable` status, because `--force` cannot fix a file
the installer cannot read. Add the kind:

```python
@dataclass(frozen=True)
class Line:
    path: str  # repo-relative, e.g. ".gitattributes"
    key: str  # the token that identifies the line, e.g. the index path
    value: str  # the rest of the line, e.g. "merge=union"
```

Statuses: `ok` (a line with `key` carries `value`), `drifted` (a line names
`key` with a different value), `missing` (no line names `key`), `unreadable`
(cannot read the file). Install appends when missing, rewrites a drifted line
only when `report.force` is set — the field plan 007 added for exactly this —
and refuses when unreadable. Local mode only: the line lives in the repo.

`Line` is not stamped and not a `Kind`; it does not render from a prompt
source. It is a separate tuple on `Host` (`lines`), checked and written by
`install` alongside `artifacts`, and it shows up in the check table under its
`path`.

### 3. Superseded artifact paths — `previous_names`

A host that renames a rule or skill leaves the old file behind at every
consumer, still auto-loading, still stamped as the host's. The first host
carries a one-off `superseded_legacy_rule` for one such rename.

Add `previous_names: tuple[str, ...] = ()` to `Rule`, `Skill`, and `Agent`.
During install, for each previous name, resolve the path it would occupy in
the install mode and remove it **only if it carries this host's stamp** — the
same test `remove_stale_local` applies to a stale local copy. A file at an old
path without the stamp is left alone and reported as a note, never removed.
`install --check` reports a stamped leftover as `stale`, which the vocabulary
already has.

### Implementation order

1. `pkgskills.precommit`: `Hook`, `wire`, `checks`, the dev-dependency helper,
   with tests through `pkgskills.testing.sandbox` and a fake `pre-commit` on
   `PATH`. Document the mode-resync and leave-alone rules.
2. `Line` on `Host`, with `unreadable` added to the check-table rendering and
   tests for all four statuses, plus the `force` gate.
3. `previous_names`, with tests that an unstamped file at an old path
   survives.
4. README: a "hooks" section, a `Line` example, and the rename recipe.
   Changelog: three Added entries. All additive; no existing host breaks.
5. Cut a minor release, then let the first host delete its remaining
   machinery.

### Out of scope

Host-declared install options (plan 007 deferred them; still one host).
Running any subprocess outside a host's explicit `after_install` or
`extra_checks`. Any hook framework other than pre-commit.

## Log

### 2026-09-11 — steps 1–4 implemented on `feature/host-install-machinery`

1. `pkgskills.precommit`: `Hook`, `wire`, `checks`, `add_dependency`, plus
   the read-only helpers (`hook_state`, `hooks_dir`, `registered`,
   `hookspath_set`). Tests drive `wire` with a fake `pre-commit` passed as
   `precommit=(python, script)` rather than placed on `PATH`, since the
   default invocation is `uv run pre-commit` in local mode and faking `uv`
   would be awkward; two tests need a real `git` for `core.hooksPath` and skip
   without one. `GIT_CONFIG_GLOBAL`/`GIT_CONFIG_SYSTEM` are pinned to devnull
   in the fixture so a developer's own `core.hooksPath` cannot leak in.
2. `Line` on `Host.lines`, with `LineStatus`, `LineCheck`, `LineWrite`,
   `check_line(s)`, `write_line(s)`. `run_check` prints line rows with a blank
   mode column and gates on them; an unreadable line file suggests no repair.
3. `previous_names` on `Skill`, `Rule`, `Agent`; `previous_paths`,
   `remove_previous`, `leftover_previous`. `check` adds a `stale` row per
   stamped leftover; a renamed skill's emptied directory is removed with it.
4. README sections for lines, hooks, and the rename recipe; changelog entries.

Decisions made while implementing, beyond the plan text:

- **`InstallReport.previous`.** The plan's resync rule ("re-syncs an entry
  that names the other mode, leaves a deliberately different one alone")
  cannot distinguish the first host's dev-repo case — `uv run <cli>` kept on
  purpose under a global stub — from a stale entry, because both name the
  other mode. The first host resolved this by resyncing only on a genuine mode
  switch, which needs the mode installed *before* the write. `install` now
  records it as `previous` (a `None` first install never resyncs either), and
  `wire` derives the rule from that instead of taking a `resync` flag.
- **Lines live at the repo root in every mode.** "Local mode only" in the
  plan is read as "never under `$HOME`", not "skipped on a global install": a
  global install of the first host still wires its `.gitattributes` line, and
  the line is repo content whatever the mode.
- **`unreadable` overflows the status column** rather than the table widening:
  the eight-character column is pinned by existing tests and the case is rare.
- **`hookspath_blocked` / `blocked`** are kept as a fifth state on both sides,
  since the first host needed the distinction to name the real cause.
- **A single-source skill cannot be renamed from the declaration alone**: its
  stub lifts the source's `name`. Documented in the README; the tests rename
  the dispatcher.

### 2026-09-11 — review follow-up and close

Review of PR #8 at medium level raised nine findings; all were actioned in
`ed8c272`, each with a regression test, and the README and changelog were
brought in step in `9517c3f`.

- **Config with no content.** `wire` seeded `repos:` only when the file was
  absent, so an empty or comments-only config received a hooks block with
  nothing to hang under. Now seeded whenever the config has no content line.
- **Hook presence by substring.** `hook.id in text` read `x-index` as present
  next to `x-index-all`, in both `wire` and `hook_state`. Presence is now the
  `- id:` line, matched with an anchored pattern.
- **Unquoted YAML scalars.** `name` and `files` are free text that may carry
  `: ` or ` #`; both are now single-quoted, with `'` doubled. Flagged as
  plausible rather than reproduced, fixed because the regex case is realistic.
- **Git once per call.** `checks` and `wire` re-ran `git rev-parse` and
  `git config` per hook or per stage; a `Clone` snapshot now reads the clone
  once, and `hook_state` accepts it along with the config text.
- **One read per edit.** `write_line` and `leftover_previous` read each file
  twice; the verdict and the edit now share one read, which also removes the
  window the force-branch assertion sat in.
- **Duplicated note text** in the CLI folded into one helper; a dead
  duplicate `write_text` line dropped from a test.

Conscious no-op: the `--force` repair hint for a merely `missing` line. It
matches the pre-existing hint for a missing artifact, and `--force` is inert
when nothing else needs overwriting.

`pyyaml` was added to the dev group explicitly, since the new quoting test
parses a rendered block; before, it arrived only through `pre-commit`.

## Retrospective

- **The plan's resync rule was underspecified**, and the first host's own
  history supplied the missing case (a dev repo keeping `uv run <cli>` under a
  global stub). Recording the previous mode on the report was the smallest
  thing that made the rule decidable; reading the host that motivated a
  feature before generalizing it is worth the detour.
- **Text-append editing without a parser** is the right trade for a file the
  host does not own, but every substring test in it is a hazard. The review
  found two (`id` as a prefix, an empty file with no root key) that the
  original tests did not, because the tests only ever started from a config
  the code itself had written. Seed negative tests from files the tool did not
  create.
- **Per-item helpers hide per-call cost.** `registered`, `hookspath_set`, and
  `hooks_dir` each read naturally in isolation and each cost a subprocess;
  composing them per hook multiplied that silently. A snapshot object with the
  same public helpers kept the API and removed the multiplier.
- **"Local mode only" needed a second reading** before it meant anything
  concrete; deciding it meant "never under `$HOME`" rather than "skipped on a
  global install" was the right call, and belonged in the plan text sooner.
- **Next**: cut the minor release, then let the first host delete its
  remaining hook, line, and rename machinery against the new API.
