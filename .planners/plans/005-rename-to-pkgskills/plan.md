---
id: 5
slug: rename-to-pkgskills
status: draft
branch:
created: 2026-09-11T09:53:29-07:00
concluded:
pr:
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

1. Add a pending trusted publisher for `pkgskills` on PyPI first. It runs the same name
   check that refused `mli`, so the rename is not done against a name that gets
   refused too. A pending publisher does not reserve the name, so publish soon after.
2. Package move and import rewrite; run the test suite.
3. pyproject, version lookup, and stamp format; update the tests that assert the
   stamp text.
4. Prose and docs; grep the tracked tree for leftover `mli` outside `.planners/` and
   past changelog entries.
5. Rename the GitHub repo and the remote.
