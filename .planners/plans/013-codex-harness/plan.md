---
id: 13
slug: codex-harness
status: active
branch: feature/codex-harness
created: 2026-10-28T10:18:56-07:00
concluded:
pr:
---

# Add a Codex harness and permission guidance

## Plan

pkgskills defines one harness, `CLAUDE_CODE` (`pkgskills/harness.py`), so a package
built on it installs skills, rules, and agents only where Claude Code reads them. A
Codex session working in a consumer repo never sees them: it was observed falling back to
searching the filesystem for a skill's instructions, because no stub told it to run the
package's `skill <subcommand>` command. Packages also generate permission profiles for
Claude Code only.

The fix belongs here, not in each package: every package built on pkgskills gets it.

### Approach

1. **A Codex harness.** Add a `CODEX` `Harness` with the locations Codex reads: a skill
   directory where Codex supports one, and otherwise an `AGENTS.md` pointer that names
   the package's skill command. Check the current Codex documentation for the supported
   locations first; record what was found in the Log.
2. **Install to both.** `install` writes the stubs for each harness that supports the
   artifact kind, using `Harness.supports`.
3. **Permission guidance for Codex.** Codex's `workspace-write` sandbox is believed to
   keep `.git` read-only, which would block every commit a lifecycle command makes. Not
   verified: confirm against the Codex docs, then document which commands cannot run
   sandboxed and must be approved or run outside the sandbox, next to the Claude
   permission profiles.

### Order

Harness (1), then install (2), then the guidance (3), each with tests against a
temporary home and project directory.

### Out of scope

- Codex support in any single consuming package; it follows from this.

## Log

- **2026-10-29T10:37:02-07:00** — Activated.
  - Branch: `feature/codex-harness`
  - Base: `dev` at `a67b79f`
  - Worktree: `.worktrees/013-codex-harness`
  - PR: pending
