"""Subprocess calls pinned to a repo root, immune to git's location variables.

``pkgskills`` itself runs no subprocesses. :attr:`Host.after_install
<pkgskills.host.Host.after_install>` exists so a host can, and the motivating case —
wiring a pre-commit hook — shells out to git. Every host that does hits the same
hazard, so the guard belongs here rather than in each of them.

Passing ``cwd=root`` is not enough to say which repository a command is about.
Git's location variables — ``GIT_DIR`` and friends — outrank ``cwd``, so an
inherited one silently redirects the command to a different repository: files land
in the tree the user was looking at while the commit lands in someone else's
history. That is a reachable state, not a hypothetical. Git exports ``GIT_DIR`` to
every hook it runs, so a host CLI invoked from a hook, a wrapper script, or a shell
where an earlier command left the variable set inherits it. Nothing warns.

**An ambient ``GIT_DIR`` is never honored here, deliberately.** The target
repository is named by ``root``, and only by ``root``. Honoring the variable would
put the files in one repo and the commit in another, which is the bug itself.

:func:`pkgskills.artifacts.find_repo_root` has the matching posture on the read side: it
walks the filesystem for ``.git`` rather than asking git where it is. Between them,
neither the location a host reads nor the repository it writes to can be moved by
the environment.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Sequence
from pathlib import Path

__all__ = [
    "LOCATION_ENV",
    "pinned_env",
    "run",
]

# The variables that relocate git's idea of "the repository". Stripped for the
# duration of every call so ``root`` is the only thing that selects a repo.
# ``GIT_CONFIG_*`` and ``GIT_CEILING_DIRECTORIES`` are deliberately *not* here:
# they change what git reads, not which repository it acts on, and test suites
# rely on setting them.
LOCATION_ENV = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_COMMON_DIR",
    "GIT_OBJECT_DIRECTORY",
)


def pinned_env() -> dict[str, str]:
    """The current environment minus :data:`LOCATION_ENV`."""
    return {k: v for k, v in os.environ.items() if k not in LOCATION_ENV}


def run(
    root: Path,
    argv: Sequence[str],
    *,
    capture_output: bool = False,
) -> subprocess.CompletedProcess[str]:
    """Run ``argv`` in ``root`` with the git location variables stripped.

    Never ``shell=True`` and never ``check=True``: callers decide what a non-zero
    exit means (for the ``rev-parse --verify -q`` forms it just means "no such
    ref"), and they translate the raising failures — a missing binary, which is
    ``FileNotFoundError`` — into their own idiom. Output goes to the caller's
    terminal unless ``capture_output``.
    """
    return subprocess.run(
        list(argv),
        cwd=root,
        capture_output=capture_output,
        text=True,
        env=pinned_env(),
    )
