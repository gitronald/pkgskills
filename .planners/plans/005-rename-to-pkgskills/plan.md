---
id: 5
slug: rename-to-pkgskills
status: done
branch: feature/rename-to-pkgskills
created: 2026-09-11T09:53:29-07:00
concluded: 2026-09-11T10:32:44-07:00
pr: https://github.com/gitronald/pkgskills/pull/1
---

# Rename the package to pkgskills

## Plan

### Why rename

PyPI refuses to register `mli`: "This project name is too similar to an existing
project." Its similarity check folds separators and look-alike characters (`l`/`i`/`1`,
`o`/`0`) together, so a three-letter name made of `m`, `l`, and `i` collides even though
no project is registered under `mli` exactly. The package has never been published, so
the name has to change before the first release.

`pkgskills` names what the package is for: a CLI keeps its skills **inside its own
package** as package data, released and versioned with it, and the harness gets only
thin stubs that load the packaged body back. The `pkg` prefix echoes `pkgutil` and
`pkg_resources`, the standard tools for reading resources shipped inside a package.

Alternatives weighed:

- `cli-skills`: available, but the import would be `cli_skills` while the distribution
  is `cli-skills`, and it reads as a collection of skills rather than the tooling.
- `skillcli`: one character away from the registered `skills-cli`, and reads as a
  tool for managing skills.
- `skillship`: available and fitting, but it names the effect, not the mechanism.
- `mlikit`: keeps `mli` as the import and changes only the distribution name, which is
  the least churn but leaves the install name and the import name mismatched.

### Scope

One name everywhere: distribution, import package, and console script.

- **Package:** `git mv mli pkgskills`, then rewrite `import mli` / `from mli` across
  the package, tests, and fixtures.
- **pyproject.toml:** `name`, the `[project.scripts]` entry (`pkgskills =
  "pkgskills.cli:..."`), the sdist `only-include` path, coverage `source`, and the
  repository URL.
- **Version lookup:** `stamp.py` reads its own version with
  `metadata.version("mli")`. That must follow the distribution name or it raises
  `PackageNotFoundError` once installed as `pkgskills`.
- **Stamp format:** the stamp line (`via mli X`) and the `mli-version` metadata key
  become `via pkgskills X` and `pkgskills-version`. A key rename is a content change
  rather than a masked version token (see plan 004), so every stub installed from a
  git pin reports drift once and needs a `--force` reinstall. Acceptable, since nothing
  is on PyPI yet; note it in the changelog.
- **Prose:** README (title, install lines, examples), CHANGELOG (an `[Unreleased]`
  entry for the rename), `docs/`, and the project `CLAUDE.md` package tree. Drop or
  rephrase "model line interface" where it served only to expand `mli`.
- **Tests:** rename `tests/test_mli_cli.py` and any `mli_app` identifiers that carry
  the old name.
- **Repo:** `gh repo rename pkgskills` (GitHub redirects the old URL), then update the
  local `origin` remote.

### Out of scope

- Rewriting existing plans or the changelog's past entries. They record the package
  under the name it had at the time.
- Plan 004's version-key question. This plan renames the key it already writes; it
  does not change what the key means.

### Implementation order

1. Rename the GitHub repo and the local `origin` remote. The trusted publisher in
   step 2 is bound to an owner/repo name, so the repo must carry its final name
   before the publisher is configured.
2. Add a pending trusted publisher for `pkgskills` on PyPI, pointing at the renamed
   repo. It runs the same name check that refused `mli`, so the rename is not done
   against a name that gets refused too. A pending publisher does not reserve the
   name, so publish soon after.
3. Package move and import rewrite; run the test suite.
4. pyproject, version lookup, and stamp format; update the tests that assert the
   stamp text.
5. Prose and docs; grep the tracked tree for leftover `mli` outside `.planners/` and
   past changelog entries.

## Log

### 2026-09-11

- Step 1: the GitHub repo is now `gitronald/pkgskills`, and the local `origin`
  points at the new URL.
- Step 2 (pending PyPI trusted publisher) happened outside the repo, so this
  branch does not record it.
- `83a2f11` rename package, script, and stamp to pkgskills: `git mv mli
  pkgskills`, import rewrite, pyproject (name, script, sdist path, coverage,
  URL), `metadata.version("pkgskills")`, `via pkgskills` stamp line, and
  `pkgskills-version` metadata key.
- `09ead13` rename mli to pkgskills in readme, docs, and changelog, with an
  `[Unreleased]` entry noting the one-time `--force` reinstall.
- `a6f0873` rename leftover mli test name (`tests/test_mli_cli.py` became
  `tests/test_pkgskills_cli.py`).
- `d43a367` merge dev into the branch to pick up the Python 3.11-3.13 fix for
  the mutable permissions default.
- `git grep -w mli` outside `.planners/` and past changelog entries is empty.
  The built wheel ships only `pkgskills/` with the console script
  `pkgskills = pkgskills.cli:pkgskills_app`.

#### Review follow-up

A `/code-review` at medium level on PR #1 raised 9 candidates. After dedup
and verification, 3 remained:

- **README tagline** (confirmed): "Model line interface: ..." survived under
  the new title, although this plan said to drop it and pyproject already had.
  Fixed; the tagline now matches the pyproject description.
- **Prose wrap drift** (confirmed): the +6-char substitution pushed about 30
  lines in README.md and docs/ past the files' ~80-char wrap. Rewrapped with
  no word changes. The 108-char `docs/design.md:58` predates this plan and was
  left as is.
- **Duplicated entry-point group in error text** (plausible): the `hosts` and
  `check` commands hard-coded `"pkgskills.hosts"` next to
  `ENTRY_POINT_GROUP`, which the rename had to edit three times in lockstep.
  Both now echo one `NO_HOSTS` string built from the constant, and both
  nothing-registered tests assert that the group name appears (`5a31d54`).
- Conscious no-op: hard-coding `"pkgskills"` in `pkgskills_version()` was
  rejected. `metadata.version` takes the distribution name, not the import
  name, and no second literal exists to consolidate with.

## Retrospective

- The rename was almost entirely mechanical. Every real review finding came
  from treating it as find-and-replace: the substitution does not know that
  an acronym expansion only made sense for the old name, or that longer tokens
  break hard-wrapped prose.
- A rename plan should list "rewrap touched prose" and "grep for phrases that
  explained the old name" as explicit steps, alongside the leftover-token grep.
- Duplicated literals of the package's own name are a rename's real cost.
  Deriving user-facing text from the one constant that code already reads
  (`ENTRY_POINT_GROUP`) keeps the next rename to a single edit.
- Ordering the GitHub rename before the PyPI publisher, a late edit to the
  plan, was the right call. The publisher binds to owner/repo, so the other
  order would have meant redoing it.
