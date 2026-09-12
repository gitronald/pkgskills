---
id: 8
slug: host-install-machinery
status: draft
branch:
created: 2026-09-11T19:38:49-07:00
concluded:
pr:
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
