---
id: 1
slug: template-upgrade
status: done
branch: feature/template-upgrade
created: 2026-09-09T09:35:39-07:00
concluded: 2026-09-09T09:37:47-07:00
pr: null
---

# Sync repo tooling to the current project template

## Plan

Bring this repo up to the current template standard via the project template's
upgrade path. Classification: **package** (has `[build-system]`,
`project.scripts`, and a published-destined package dir), so every package row
of the sync matrix applies.

The repo has no git remote, so the PR flow and the GitHub-side Dependabot
toggles are out of scope; work lands on `feature/template-upgrade` in a
worktree and merges into `dev` locally.

### Sync decisions

| Item | Action |
|---|---|
| `.pre-commit-config.yaml` ruff rev | sync `v0.16.1` -> `v0.16.6` (stale template rev) |
| `.claude/settings.json` Stop hook `command` | replace with the `${CLAUDE_PROJECT_DIR:-.}`-anchored form (cwd-independent) |
| `.claude/hooks/lint-typecheck.sh` | replace with the current template hook (project-root walk-up, `ruff format --check`) |
| `pyproject.toml` `[tool.pytest.ini_options]` | merge template `addopts = "--cov --cov-report=term-missing"`, keep repo `pythonpath` |
| `pyproject.toml` `[tool.coverage.*]` | add; `run.source = ["mli"]`, `fail_under` set to the repo's current total |
| `pyproject.toml` dev group `pytest` | bump pin to `>=9.0.3` to match template |
| `.github/workflows/test.yml` | pin actions to commit SHAs with `# vX.Y.Z` comments; pytest step becomes bare `uv run pytest` (coverage now via `addopts`) |
| `.github/workflows/publish.yml` | pin actions to commit SHAs with `# vX.Y.Z` comments |
| `.claude/CLAUDE.md` | refresh the `## Development` Tests bullet (merged: keep the fixtures/`pythonpath` note, add the coverage gate) and add `ruff format --check .` to the "Before finishing a task" list |

### Already current — no action

`.python-version`, `.gitignore` (repo extras kept), `.github/dependabot.yml`,
`pyproject.toml` ruff/pyrefly sections and build/sdist/urls/scripts rows,
`.planners/` scaffold.

### Deliberately skipped

- Dependabot repo settings (alerts on / security updates off): no remote, so
  there is no GitHub repo to configure.
- PR step: no remote. The branch merges into `dev` with `--no-ff` locally.
- `mli/`, `tests/`, `README.md`, `CHANGELOG.md`: never touched by the matrix.

### Verify

`uv sync --all-groups`, `ruff check`, `ruff format --check`, `pyrefly check`,
`pre-commit run --all-files`, and `pytest` must all pass before this lands —
the Stop hook gates every future session on them.

## Log

- Applied every sync-decision row. The template-owned files that diverged only
  by carrying an older template revision (pre-commit ruff rev, the Stop hook
  `command`, `lint-typecheck.sh`, the workflow action pins) were replaced
  outright — nothing repo-specific was lost.
- Asked about the two `.claude/CLAUDE.md` spots the repo had customized:
  - Tests bullet -> **merge**: kept the fixtures/`pythonpath` note and added
    the template's coverage-gate wording.
  - "Before finishing a task" -> **add `ruff format --check .`**, so the
    documented list matches what the upgraded Stop hook and CI actually run.
- `fail_under` set to **96** (current total coverage 96.34%), holding the line
  rather than the template's default 50.
- The action SHAs were re-resolved from the GitHub API rather than trusted from
  the template; all five matched the template's pins.
- `uv run ruff format --check .` failed on `README.md` — a pre-existing failure
  on `dev`, not caused by this upgrade (the old Stop hook ran lint only, so it
  never surfaced). Ran the formatter; it collapsed the aligned trailing
  comments in the README's `Host(...)` example. Fixed here because the new hook
  gates every future session on it.
- No git remote on this repo, so the PR step and the GitHub-side Dependabot
  alert/security toggles were skipped; the branch merged into `dev` locally
  with `--no-ff`.
- `.claude/` is gitignored here, so `settings.json`, `hooks/lint-typecheck.sh`,
  and `CLAUDE.md` were updated on disk in the main checkout, outside this
  branch.
