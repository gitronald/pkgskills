---
id: 1
slug: template-upgrade
status: active
branch: feature/template-upgrade
created: 2026-09-09T09:35:39-07:00
concluded:
pr:
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
