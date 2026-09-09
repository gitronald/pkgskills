---
id: 2
slug: planners-install-lessons
status: draft
branch:
created: 2026-09-09T11:28:41-07:00
concluded:
pr:
---

# Backport planners install and release lessons

## Plan

`mli` generalizes the install/stamp/drift machinery that `planners` grew first.
Between planners 0.4 and 0.6 that package learned several things the general
library does not know yet — one of them from a bug that put commits in the
wrong repository. This plan brings the transferable ones across, plus two
one-line repo-hygiene fixes.

Note what is deliberately *not* here: version masking in the drift comparison
(`mask_versions` in `artifacts.classify`) is a place `mli` is already ahead —
planners still compares raw text, so a version bump flags every artifact as
drifted. Nothing to backport there.

### Scope

Six items, roughly independent. Ordered below by a mix of cost and risk: the
two hygiene fixes and the subprocess module are cheap and purely additive, the
stale-copy status is the one correctness gap in shipped behavior, the check
hook is the design change that unblocks a host migrating fully onto `mli`, and
the permissions command is the largest new surface.

Out of scope: mainline-branch detection (`base`), plan-index merge semantics,
and the plan-lifecycle commands themselves. Those are the consuming package's
domain, not a prompt-shipping library's.

---

### 1. Repo hygiene (no library code)

**1a. `dependabot.yml` needs `target-branch: dev`** for both ecosystems.
Without it, dependency PRs open against the default branch, so every batch has
to be retargeted by hand and Dependabot resolves manifests against a tree the
updates will not merge into. Because Dependabot reads its config from the
default branch, this only takes effect once the change reaches `main`.
Symptom already visible: this repo's pinned actions have drifted behind.

**1b. This repo has no `.gitattributes`**, so its tracked, generated
`.planners/README.md` has no `merge=union` and any local merge whose two sides
both touched the plan index conflicts on a generated file. The fix is to
re-run the plan tooling's installer once the machine's copy is new enough to
write the attribute (the globally installed one predates it — `install --check`
prints no `gitattr:` line).

### 2. `mli/proc.py` — pin shell-outs to a root, strip git's location variables

`mli` runs no subprocesses today, but `Host.after_install` exists precisely so
a host can shell out after an install (wiring a pre-commit hook is the
motivating case). Every host that does will hit the same hazard independently,
so the fix belongs in the library rather than in each host.

The hazard: git exports `GIT_DIR` into every hook it runs, and the location
variables outrank `cwd`. A host CLI invoked from a hook, a wrapper, or a shell
where an earlier command left the variable set inherits it, and a commit lands
in another repository's history while the files stay uncommitted where the user
was looking. Nothing warns.

Add a small module:

```python
LOCATION_ENV = (
    "GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE",
    "GIT_COMMON_DIR", "GIT_OBJECT_DIRECTORY",
)

def run(root: Path, argv: Sequence[str], *, capture_output: bool = False)
    -> subprocess.CompletedProcess[str]
```

- `cwd=root`, `env` = the current environment minus `LOCATION_ENV`.
- Never `shell=True`; never `check=True` — callers decide what a non-zero exit
  means and translate the raising failure (a missing binary,
  `FileNotFoundError`) into their own idiom.
- `GIT_CONFIG_*` and `GIT_CEILING_DIRECTORIES` stay: they change what git
  *reads*, not which repository it acts on, and test suites rely on setting
  them.
- An ambient `GIT_DIR` is never honored, deliberately. The target repository is
  named by `root` and only by `root` — honoring the variable would put the
  files in one repo and the commit in another, which is the bug itself.

`find_repo_root` already has the matching posture on the read side: it walks
the filesystem for `.git`, never asks git. Document the two together.

Re-export `run` (and `LOCATION_ENV`) from `mli.__init__` so a host's
`after_install` reaches it without importing a private module.

### 3. `--check` rows that report without gating

`install --check` currently prints one row per artifact, all of which gate the
exit code, plus ad-hoc stderr notes. Some state a host needs to surface is
per-clone and a correct consumer may legitimately lack it — hook registration
is the canonical example: a hook that never fires looks exactly like a hook
that fires and finds nothing wrong, so it earns a line, but failing the check
over it would call a correctly installed consumer broken.

`Host` has `after_install` for the write side and nothing for the check side,
so a host with extra state has to abandon `run_check`'s table and write its own
`install` command. Add the symmetric hook:

- A frozen `ExtraCheck(label: str, status: str, gates: bool, note: str = "")`.
- `Host.extra_checks: Callable[[Host, Path, Mode | None], Sequence[ExtraCheck]] | None`.
- `run_check` renders those rows in the same table, folds only `gates=True`
  rows into the exit code, and prints `note` to stderr.

Two sub-lessons to honor while building it:

- **Check the artifact, not a proxy for it.** The originating bug asked "is the
  hook runner wired into this clone" before "does the config name *our* hook",
  and so reported `active` for a hook that could never fire.
- **Keep "what an attempt did" and "what is" as separate vocabularies.** The
  status set for a write-time follow-up is not the status set for a read-only
  report; collapsing them into one overloaded enum forces a caller to
  overpromise. Applies to any `after_install` reporting `mli` grows later.

### 4. Stale local copies are drift, not a note

The gap in shipped behavior. The harness auto-loads rules and agents from the
global *and* the repo location at once, so a per-repo copy left behind after a
switch to global is an extra file live in context — even when its content
matches its render exactly. Skills differ: the global one shadows the local
one, so the local stub is merely inert.

Today `check` reports such a local copy as plain `ok`, and only the skill case
is surfaced at all (`shadowed_skills`, as a non-gating stderr note).

- Introduce a `stale` status (or reuse `drifted` with a distinguishing reason)
  for a content-ok local copy of a *simultaneously loaded* kind, once a
  resolved global install pins the repo to global.
- Gate on it. Name the path in the reason — it is loaded into context right
  now, and the remedy is to remove it, not to regenerate it.
- Guard the trigger on a genuinely resolved global install. `installed_mode`
  falls back to `global` when nothing is installed, and a local-only copy in a
  repo with no global install must keep reading `ok`.
- Keep the asymmetry deliberate: a *global* copy present during a local install
  is shared infrastructure serving every other repository, never this repo's
  leftover. Never flag it.
- The existing `$HOME`-is-the-repo-root guard still applies — the two paths
  coincide, so there is only one file.

`Kind` already carries the information needed to tell the two loading
disciplines apart; make that explicit on `Harness` (a per-kind
"global shadows local" vs. "both load") rather than hardcoding it at the call
site, since it is a property of the harness, not of `mli`.

### 5. `unreadable` as a status distinct from `missing`

`classify` folds an unreadable or non-UTF-8 file into `foreign` with the reason
`"unreadable or not UTF-8"`, and the CLI then tells the user to re-run with
`--force`. That is correct *today*, because every write is wholesale: `--force`
genuinely fixes it.

The general rule behind the originating fix is what to record: **a status must
not imply a remedy the tool cannot perform.** It bites the moment an artifact
is *edited in place* rather than rewritten — appending or amending one line of
a file the host does not own. There, an installer that cannot read the file
correctly refuses to write it, so reporting `missing` (or pointing at `--force`)
sends the user in a circle.

No code change while the artifact model is write-wholesale. The deliverable is
a note in `artifacts.py` next to `classify`, so that whoever adds an
edit-in-place artifact kind gives it `unreadable` from day one instead of
discovering it in a bug report.

### 6. A shared `permissions` command

Any host shipping skills that shell out has the same prompt-fatigue problem,
and nothing about the solution is host-specific except the rule list. Add
`mli/permissions.py` plus a `<cli> permissions` command:

- An escalating, superset ladder named by supervision posture — grant nothing /
  local and reversible / add the publishing step / add the irreversible step —
  with numeric aliases.
- The host declares only its own per-level increments; `rules_for` returns the
  cumulative union, deduplicated, in ascending-level order.
- Mode-aware, derived from `Host.invocation`: a global install needs a
  `Bash(<cli>:*)` grant, while a local install already runs under the broader
  `uv run` grant.
- Writes `.claude/settings.local.json` for local (personal, git-ignored, scoped
  to one checkout) and `~/.claude/settings.json` for global.
- **Additive merge, never a downgrade**: a rule already on `deny` or `ask` is
  left there and reported as skipped — a deliberate stricter policy always
  wins. A rule already on `allow` is a no-op. Matching is by exact rule string;
  subsuming a broader pattern is the harness matcher's job. The input block is
  never mutated; return a new block plus a report of added / already / skipped.
- Print-only by default, `--apply` to write, so the command is safe to run
  blind. A no-op apply prints that nothing changed rather than rewriting the
  file.

### Implementation order

1. Item 1 (hygiene) — independent, lands first.
2. Item 2 (`proc`) — additive, no existing behavior touched.
3. Item 5 (comment) — trivial, folds in anywhere.
4. Item 4 (stale copies) — the behavior change; needs its own tests and a
   changelog entry, and is the one item a consumer will notice.
5. Item 3 (extra checks) — API addition on `Host` and `run_check`.
6. Item 6 (permissions) — largest surface; benefits from 3 being settled first.

Items 2–6 each need tests and a `CHANGELOG.md` entry. Coverage must stay above
the `fail_under` floor, and `ruff check` / `ruff format --check` / `pyrefly
check` must pass before each commit.
