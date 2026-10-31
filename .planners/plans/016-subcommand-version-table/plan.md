---
id: 16
slug: subcommand-version-table
status: implemented
branch: feature/subcommand-version-table
created: 2026-10-31T15:51:53-07:00
concluded:
pr: https://github.com/gitronald/pkgskills/pull/29
---

# Add a version column to the dispatcher's subcommand table

## Plan

Moved out of plan 010, which shipped this with the stamp migration. The two share
no code, so this no longer waits for that one.

### The dispatcher's subcommand list becomes a table

Turn the bulleted `Subcommands (N):` list in a dispatcher stub into a table with
a version column:

```
| Subcommand | Version | Description |
|---|---|---|
| `add` | 1.0.0 | Scaffold a new plan file. Use when … |
| `implement` | 1.0.0 | Start implementing a plan — … |
```

- The version is the source's own `metadata.version` (plan 004's key), read
  from each source's frontmatter the same way the description is today. A
  source that declares none gets an empty cell, never a fallback to the host
  release, for 004's reason: one column meaning two things is the ambiguity
  that plan removed.
- This is the first place a per-skill version becomes *visible* after
  install; today a dispatcher's sources carry it only in the package. It is
  body text, so a version bump in one source drifts the stub as 004 intends,
  and `mask_versions` leaves it alone.
- A single-source stub is unchanged: its version already rides in the lifted
  frontmatter block.
- The "map to `/<skill> <sub>`" sentence and the `skill --list` fallback stay
  as they are, below the table.

### Implementation order

1. `rendering.py`: the dispatcher tail renders the subcommand table, reading
   `metadata.version` per source.
2. Tests: `test_render.py` covers a source with a version and one without.
3. Docs: plan 009 left a dispatcher stub documented as never receiving a
   source's metadata, so revise the dispatcher paragraphs in `docs/frontmatter.md`
   and the README's host guide. Changelog under `[Unreleased]`.

## Log

- **2026-10-31T16:55:14-07:00** — Activated.
  - Branch: `feature/subcommand-version-table`
  - Base: `dev` at `16a8a12`
  - Worktree: `.worktrees/016-subcommand-version-table`
  - PR: pending
- **2026-10-31T16:58:03-07:00** — PR opened: https://github.com/gitronald/pkgskills/pull/29
- **2026-10-31T16:58:04-07:00** — Implemented: 3 commits ahead of `dev`.
