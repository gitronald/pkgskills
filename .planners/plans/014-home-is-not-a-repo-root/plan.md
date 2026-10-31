---
id: 14
slug: home-is-not-a-repo-root
status: implemented
branch: feature/home-is-not-a-repo-root
created: 2026-10-31T14:10:56-07:00
concluded:
pr: https://github.com/gitronald/pkgskills/pull/26
---

# Stop treating the home directory as a repository root

## Plan

### Problem

`find_repo_root` treats any declared harness config directory as a repository
marker. `~/.claude` and `~/.codex` are the global install's own location, so on any
machine with a global install, every directory under home that no nearer marker
claims resolves to `$HOME` as its "repository". There, local and global paths name
the same files. Plan 009 documented the walk for hosts' own commands and left the
mounted commands alone; running them shows the result is a bug in this library.

Run against the `examplehost` fixture with a sandboxed `$HOME`, from `~/notes/deep`
with no repository:

- **A healthy install fails its check.** After `install --global`, a flagless
  `install --check` judges each file twice. The global row reads `ok`, the local row
  reads `drifted (rendered for mode=global, installed where mode=local)`, and it
  exits 1.
- **The repair it prints does the damage.** The check prints
  `repair: uv run <cli> install --local --force`. A local install there overwrites
  the global stubs in place and exits 0, and it does not need `--force`, because the
  files are the host's own. The stubs are then stamped `mode=local` and tell every
  repository on the machine to run `uv run <cli>`. The output gives the paths
  relative to the root, so it never shows that the target was home.
- **A released host does the same.** A host on pkgskills 0.5.1, with a healthy global
  install, printed the same rows and repair from a directory under home and exited 1.
  Its `Line` and hook rows also read `missing` there (see the open question below).
  That was a read-only `--check` against a real home directory.

The same double verdict appears with no walk involved: from `$HOME` itself, and from
anywhere under a home that holds `.git` (a dotfiles repository). So the walk is one
of two causes, and fixing it alone leaves the second.

The code already knows about the coincidence. `stale_local`, `shadowed_skills`, and
`remove_stale_local` each guard on the two paths being equal, and plan 002 calls this
the "`$HOME`-is-the-repo-root guard". `check` and `install` have no such guard.

### Decisions

1. **Home's harness directory is not a marker.** In `find_repo_root`, a harness
   config directory marks a root everywhere except at the home directory. `.git` at
   home still does, so a dotfiles repository keeps its root. From `~/notes/deep` the
   walk then falls back to `start`, as it does outside home.
   - Compare against `Path.home().resolve()`, since the walk resolves its start and
     `$HOME` can be a symlink.
   - `Path.home()` raises `RuntimeError` where no home can be determined, which
     `global_base` exists to defer. Catch it and apply no exclusion, so a local-only
     host on such a machine keeps working.
   - The alternative of leaving the walk alone and refusing `--local` at home was
     rejected: it would keep a healthy directory's root wrong for `doc`, `skill`,
     `rule`, `agent`, and `permissions`, and for every host command that follows the
     guidance plan 009 published.
2. **Where the two paths coincide, there is one location, and it is the global one.**
   This covers what decision 1 cannot reach: a root that really is `$HOME`.
   - `check` judges a coincident path once, as global, so a healthy install reads
     `ok`. A file already stamped `mode=local` there reads `drifted`, and its repair
     is the global install.
   - For a host with both modes, `--local` is refused when any of its paths coincide,
     for both `install` and `install --check`, and `pkgskills.install` raises the same
     `ValueError` a caller gets for a mode the host does not support. This follows
     `_requested_mode`: naming the wrong mode is an error, not a silent redirect.
   - A local-only host is exempt. It has no global copy to overwrite, and its only
     location is the one it asked for.
3. **Hosts' guidance flips back.** The README's "Your own commands" and the
   `find_repo_root` docstring now describe home as a marker. They should say that the
   walk does not stop at home's harness directory. The repository guard stays, since
   the walk still returns a directory outside any repository.

### Implementation order

1. `artifacts.py`: the walk (decision 1) with its tests.
   `test_find_repo_root_stops_at_a_harness_directory_in_home` inverts, and
   the comment on home in `test_the_documented_repository_guard` goes. New cases:
   a symlinked `$HOME`, `~/.git` still a root, and `Path.home()` raising.
2. `artifacts.py` and `cli.py`: the coincidence (decision 2). `test_no_stale_removal_when_repo_root_is_home`
   installs locally at home first, so it now writes that file directly. New cases, at
   a root of `$HOME` with and without `.git`: a flagless check reads one `ok` row per
   file and exits 0, a `mode=local` file there reads `drifted` with the global repair,
   `install --local` refuses and leaves the files alone, and a local-only host still
   installs.
3. An end-to-end test through the mounted commands from a directory under home:
   check passes, and `install --local` writes under that directory and leaves the
   global stub stamped `mode=global`.
4. Docs: README "Your own commands", the `find_repo_root` docstring, and
   `docs/design.md`'s Anchoring decision. Changelog under `### Fixed`, naming the
   recovery for a clobbered install: the check now reports it, and `install --force`
   from a repository repairs it.

New tests need the `no_outer_git` fixture from `tests/test_install.py`. Once the walk
passes home it can reach a stray `.git` in a parent of the temporary directory, and
one exists on at least one development machine.

### Out of scope

- `install --local` outside a repository still writing to `start`. That fallback is
  documented and tested, and it is what a first install before `git init` relies on.
- `permissions`: its local and global settings paths differ, so nothing coincides.
  Decision 1 corrects where its local file goes under home.

## Log

- **2026-10-31T14:21:41-07:00** — Relation to earlier decisions: decision 1 here replaces part of plan 009, and this plan supersedes that part. Recommended: still do it.
  - Reversed from plan 009: decision 1's "the fallback stays as it is", and the docs and test that describe the walk stopping at `$HOME` as expected. Plan 009's out-of-scope line on the install and check flow was a scope limit, not a judgement that the flow was sound.
  - Why it does not hold: that call concerned hosts' own commands and was made without running the mounted ones, which recorded the risk as unverified. Running them showed the check suggesting a repair that overwrites the global stubs. The wording is unreleased, on `dev` and under `[Unreleased]`, so reversing it costs little.
  - Unchanged: `register` mounts no callback, hosts pass `harnesses`, the README's repository guard stays, and plan 009's other decisions stand. Plan 002's guard for `$HOME` as a root is extended, not undone.
  - Narrower option: decision 2 alone reverses nothing and stops both the false failure and the overwrite. Only decision 1 reverses plan 009. Doing both is recommended, because with decision 2 alone a local install under home is refused rather than placed there, and host commands following the README still get `$HOME` as their root. Decision 2 alone remains a safe first step if the walk change is deferred.
- **2026-10-31T14:30:16-07:00** — Activated.
  - Branch: `feature/home-is-not-a-repo-root`
  - Base: `dev` at `23c4015`
  - Worktree: `.worktrees/014-home-is-not-a-repo-root`
  - PR: pending
- **2026-10-31T14:33:20-07:00** — PR opened: https://github.com/gitronald/pkgskills/pull/26
- **2026-10-31T14:35:45-07:00** — Implemented all four steps. Departures from the spec, and what running it showed:
  - **Second cause of the same class, not in the plan.** The guards compared built paths, a resolved root with an unresolved home. Under a symlinked `$HOME` holding `.git`, they did not fire: run against the code before this plan, a global install deleted the four stubs it had just written and reported them as stale local copies. `root_is_home` resolves both sides and replaces the three comparisons, and a regression test pins it. Reproduce it with a home that is a symlink to a directory holding `.git`, then a global install from there.
  - **Coincidence is decided on the root, not per path.** Both modes share one relative layout, so a root at home makes all of a host's paths coincide or none. `location_modes(host, root)` is the single answer, used by `check`, `installed_mode`, `printing_mode`, `skill_stub_paths`, and the leftover notes. `require_mode` carries the refusal for `install` and the CLI.
  - **A flagless install on a local-first host is refused at home too.** Decision 2 names `--local`. A bare `install` on a host declaring `modes=("local", "global")` means local, so it would have done the same overwrite. It gets the refusal, which names `--global`. Its flagless check is not refused. `check`'s `missing` fallback now uses the first location mode, since the host's default would have produced no row there.
  - **`check(host, root, "local")` called directly is unchanged at home.** An explicit mode judges that one location, as it always has. The CLI refuses before reaching it.
  - **The fixture is renamed `no_outer_markers` and moved to `tests/conftest.py`.** The plan's `no_outer_git` hid only `.git`, and the first run of the new tests stopped at a stray harness directory above the temporary directory. It now hides `.git`, `.claude`, and `.codex` above it.
  - **Docs beyond the plan's list:** README's Modes section said the two locations never collide, and the `[Unreleased]` line saying the walk can stop at `$HOME` was no longer true. Both are corrected.
  - **Verified:** full suite, 391 passed, coverage 98.69%, with ruff and pyrefly clean. The plan's reproduction also ran as real processes with a sandboxed `$HOME`: from a directory under home the check exits 0 with `ok` rows only, `install --local` writes under that directory and leaves the global stub at `mode=global`, and from home `--local` and `--local --check` both exit 1. With `.git` added at home, the check from a fresh subdirectory exits 0 and `--local` is refused.
  - **Not changed:** a harness directory above home still marks a root, as any other directory's does. This only arises on a machine with such a directory in a parent of home.
- **2026-10-31T14:36:02-07:00** — Implemented: 6 commits ahead of `dev`.

## Handoff

State: all four steps are committed and pushed on the plan's branch, with the PR open.
Nothing is uncommitted. The Log entry for the implementation says what departed from
the spec and what was verified.

Open questions:

1. **Should a host's `Line` rows count outside a repository?** Measured on this branch:
   a host declaring a `.gitattributes` line, with a healthy global install, run from a
   directory under home with no repository, prints `ok` for each stub and `missing` for
   the line, and exits 1. The repair it prints, `install --force`, would write the line
   file into that directory. Skipping lines when no `.git` is at or above the root looks
   right for `.gitattributes`, but a `Line` can name any file, and a directory rooted by
   `.claude/` alone is a legitimate root. Recommended: leave the behaviour as it is here
   and take it as a follow-up plan. Waits on the maintainer, at the review gate.

Not verified: the fix against a released host. Its stubs were only run with the fixture
hosts, because hosts get it through a new `pkgskills` version.

Order: review gate, close, then release.
