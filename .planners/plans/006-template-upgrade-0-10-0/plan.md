---
id: 6
slug: template-upgrade-0-10-0
status: done
branch: feature/template-upgrade-0-10-0
created: 2026-09-11T10:42:20-07:00
concluded: 2026-09-11T10:44:07-07:00
pr: https://github.com/gitronald/pkgskills/pull/2
---

# Sync tooling to proj-template 0.10.0

## Plan

Bring this repo up to proj-template 0.10.0 via the template's upgrade path.
Classification: **package** (`[build-system]`, `project.scripts`, a
PyPI-destined package dir), so every package row of the sync matrix applies.
Work lands on `feature/template-upgrade-0-10-0` in a worktree and goes to `dev`
by PR.

### Sync decisions

| Item | Action |
|---|---|
| `.github/workflows/test.yml` | sync: `setup-uv` `v9.0.0` -> `v10.0.1` SHA pin; add `--python ${{ matrix.python-version }}` to `uv sync` with the template's comment (stale template rev) |
| `.github/workflows/publish.yml` | sync: `setup-uv` `v9.0.0` -> `v10.0.1` SHA pin |
| `.github/dependabot.yml` | sync: template header comment and `target-branch` key placement; `dev` exists on the remote |
| `pyproject.toml` sdist `only-include` | merge the template's "Not exhaustive" comment on hatchling's force-included files |
| `pyproject.toml` `[tool.proj-template]` | add after `[project.scripts]`, stamped `0.10.0`, written last |
| Dependabot repo settings | alerts turned on; security updates confirmed off |

### Already current — no action

`.pre-commit-config.yaml`, `.python-version`, `.claude/settings.json`,
`.claude/hooks/lint-typecheck.sh`, `.planners/` scaffold, and the
`pyproject.toml` ruff, pyrefly, dev-group, pytest, coverage, build, urls, and
scripts rows.

### Kept as repo customizations

- `.gitignore`: repo-only entries (local notes); the template adds nothing.
- `.claude/settings.local.json`: the template adds no entries; the repo's three
  extra grants stay, so a merge is a no-op.
- `.claude/CLAUDE.md` Tests bullet: customized with the fixtures `pythonpath`
  note; left as is.
- `pyproject.toml`: pyrefly `search-path`, pytest `pythonpath`, the `hatchling`
  dev dep, `license`, and `fail_under = 96` (above the template's default 50).

### Deliberately skipped

`pkgskills/`, `tests/`, `README.md`, `CHANGELOG.md`: never touched by the matrix.

### Verify

`uv sync --all-groups`, `ruff check`, `ruff format --check`, `pyrefly check`,
`pre-commit run --all-files`, and `pytest` must pass, and `uv build` must still
produce an sdist and a wheel that hold only the package and top-level docs.

## Log

- The CI workflows and `dependabot.yml` diverged only by carrying an older
  template revision, so they were replaced outright. The `setup-uv` `v10.0.1`
  SHA was re-resolved from the GitHub API and matched the template's pin.
- No file fell into the ask-first class: every repo-side divergence was a pure
  addition the template does not touch, so each merge kept the repo's version.
- Dependabot alerts were off; turned on and verified (204). Security updates
  were already off.
- Reviewed what the dists ship. The wheel holds only `pkgskills/` and
  `.dist-info`. The sdist adds `README.md`, `CHANGELOG.md`, `LICENSE`, and
  hatchling's force-included `pyproject.toml`, `PKG-INFO`, and `.gitignore`,
  which cannot be excluded. `pkgskills/testing.py` stays: the README documents
  it as public API for host packages' tests. Nothing further to exclude.
- All checks passed (229 tests, 98.17% coverage), so the stamp was written
  as `0.10.0`.
- 2026-09-11 review follow-up: a minimal inline pass over the PR diff (at the
  owner's request, no reviewer fan-out) raised no findings. CI passed on
  Python 3.11-3.14.

## Retrospective

- Most of this upgrade was already done: plan 001 had brought the repo close to
  the template, so the diff came down to one action-pin bump, one CI flag, and
  comments.
- The divergence triage paid off. Every repo-side difference was a pure
  addition, so no merge needed a question and none of the repo's customizations
  were at risk.
- Building the dists answered the exclusion question better than reading the
  config would have. That check is cheap enough to repeat on every upgrade.
- Leftover state from the earlier rename (a venv and a pre-commit hook still
  pointing at the old path) was found and fixed just before this upgrade. A
  directory rename needs its own cleanup pass.
