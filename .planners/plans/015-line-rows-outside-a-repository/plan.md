---
id: 15
slug: line-rows-outside-a-repository
status: draft
branch:
created: 2026-10-31T14:47:00-07:00
concluded:
pr:
---

# Decide what a host's lines mean outside a repository

## Plan

### Problem

A host that declares a `Line` fails `install --check` from a directory outside any
repository, even with a healthy global install. Measured with a host declaring a
`.gitattributes` line, from a directory under home with no repository: each stub reads
`ok`, the line reads `missing`, and the check exits 1. The repair it prints,
`install --force`, would write the line file into that directory.

This holds for any directory with no repository, under home or not. Plan 014 settled
where the root is and left this alone: before it, the same check reported the line
against `$HOME`.

### Question to settle first

What is a line for, and does it mean anything outside a repository? Skipping lines when
no `.git` is at or above the root looks right for `.gitattributes`, but:

- A `Line` can name any file, not only one git reads.
- A directory rooted by `.claude/` alone is a legitimate root, and a host may want its
  line there.

The design should come from what declaring hosts use lines for. Options to weigh:

1. Skip lines for every host when no `.git` is at or above the root, in both `check` and
   `install`.
2. Let a `Line` declare whether it needs a repository, defaulting to what most hosts want.
3. Keep the row, but stop it gating the check and stop the repair writing outside a
   repository.

### Implementation order

1. Survey the lines that declaring hosts ship, and choose an option.
2. Change `check_lines`, `write_lines`, and `run_check`'s repair hint, with tests from a
   non-repository directory and from a root marked only by a harness directory.
3. Update the README and the changelog.

## Log

- **2026-10-31T14:59:10-07:00** — Survey finished. Chosen: lines and hook wiring follow one rule, nothing is written outside a repository, and a non-gating row says why. This combines option 1's write behaviour with option 3's visible row. Not implemented.
    - Scope: the six hosts with a `pkgskills.hosts` entry point in the repositories on one development machine, loaded through that entry point. Hosts elsewhere were not surveyed, and `pkgskills` is a public library.
    - One of the six declares a `Line`: planners, with `.planners/README.md merge=union` in `.gitattributes`. Git is the only reader of that line. No host declares a line in a file that means anything without git. One other host calls `check_lines` from its own diagnostic command and declares no lines, so a change there reaches it only through the function's return value.
    - The type's own contract already says repository: the `Line` docstring and the README both describe a repository file. The shape also limits what it can name, since a blank value is refused, so a `.gitignore` entry cannot be declared. A file like `.tool-versions` would fit and would mean something without git, but no host declares one. A per-line field (option 2) stays an additive change if one appears, so it is not worth building now.
    - The survey found the plan's scope too narrow. Measured with planners at its development version on this `pkgskills` at `0.5.2a0`, under a sandboxed `$HOME`:
      - Global install from a repository, then a check from a bare directory: the line reads `missing`, both hook rows read `missing` with a note to run install, and it exits 1. The printed repair exits 0 and writes `.gitattributes` and `.pre-commit-config.yaml` there. The next check exits 0, so the repair silences the failure by adding the two stray files.
      - `install --global` run directly from a bare directory writes the same two files, with no repair involved.
      - A shared temporary directory on the same machine holds this pair, dated weeks before this plan, so it has happened outside a test.
    - The second file comes from `precommit.wire`, not from a host, so changing `write_lines` alone leaves it.
    - `hook_state` reads the config before the repository, so outside a repository a hook with no entry reads `missing`, not `no_git_repo`, and its note asks for the install that writes the stray config. Once the config exists it reads `no_git_repo`.
    - `is_git_repo` looks only at the root. At a root marked by a harness directory below the top of a repository, install prints `pre-commit hook: no git repo` from inside a repository.
    - Decisions for implementation:
      1. One predicate: `.git` at the root or above it, the guard the README already tells hosts to use. It replaces `is_git_repo` and is a filesystem walk, as `find_repo_root` is.
      2. `check_lines` returns a new `no_git_repo` status where the predicate fails. The row prints like the hook rows, counts as `ok`, and adds no repair.
      3. `write_lines` writes nothing there, and install says so.
      4. `precommit.wire` writes no config there, and `hook_state` tests the repository before the config.
    - Cost accepted: `install --local` followed by `git init` no longer leaves the line in place. The next check reads `missing` and exits 1, and the repair writes the line. That step is loud and repairable, while the stray files are silent. Reinstalling there should also register the hooks, which today's flow leaves as `unregistered`; this comes from reading the code and is not measured.
    - Hosts need no change. Their tests are unaffected as long as they use `pkgskills.testing.sandbox`, whose repository has a `.git`.
    - Step 2 of the implementation order therefore also covers `precommit.py`, with tests from a bare directory, a root marked only by a harness directory, and a harness-marked root below the top of a repository.
