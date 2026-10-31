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
