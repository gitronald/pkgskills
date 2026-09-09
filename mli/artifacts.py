"""Materialize, locate, and drift-check generated artifacts.

Two install modes, both first-class:

* **global**: one copy under ``$HOME`` serves every repository; the host CLI
  is on ``PATH`` and invoked bare.
* **local**: the copy lives under the repository root and the CLI is invoked
  through ``uv run`` (or the host's ``local_prefix``).

A file's mode is the one its location implies. A copy rendered for one mode
and carried to the other location reads as drifted, because the commands
embedded in it are wrong where it sits.

Every write is guarded. A path occupied by anything that is not a plain file
this host generated (a hand-written file, a symlink, a directory, another
package's stamp) is *foreign* and is never replaced without ``force``. The
guard runs for every artifact before the first write, so a refused rule never
leaves a half-installed skill behind.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from mli.harness import Harness
from mli.host import MODES, Artifact, Host, Mode, Skill
from mli.rendering import render
from mli.stamp import is_stamped, mask_versions, stamped_by, stamped_mode

Status = Literal["ok", "drifted", "stale", "missing", "foreign"]


class ForeignArtifactError(Exception):
    """A write was refused because the target is not ours to replace."""

    def __init__(self, path: Path, reason: str) -> None:
        super().__init__(f"{path}: {reason}")
        self.path = path
        self.reason = reason


@dataclass(frozen=True)
class Check:
    """The drift verdict for one artifact at one location."""

    artifact: Artifact
    mode: Mode
    path: Path
    status: Status
    reason: str = ""

    @property
    def ok(self) -> bool:
        return self.status == "ok"


@dataclass(frozen=True)
class InstallReport:
    """What an install did, for the CLI to narrate and hooks to act on."""

    host: Host
    mode: Mode
    root: Path
    written: tuple[Path, ...] = field(default_factory=tuple)
    removed: tuple[Path, ...] = field(default_factory=tuple)
    shadowed: tuple[Path, ...] = field(default_factory=tuple)


# -- locations ---------------------------------------------------------------


def global_base() -> Path:
    """The base of every global artifact: the user's home directory.

    A function rather than a constant so importing the package never resolves
    the home directory, which raises where none can be determined.
    """
    return Path.home()


def find_repo_root(start: Path | None = None, harness: Harness | None = None) -> Path:
    """The nearest directory at or above ``start`` that looks like a repo root.

    A repo root holds ``.git`` or the harness's config directory. A local
    install must target the root the harness loads from, not whatever
    subdirectory the command ran in. Falls back to ``start`` itself.

    Deliberately a filesystem walk, never a question put to git: an ambient
    ``GIT_DIR`` would otherwise name a repository the user is not looking at.
    :mod:`mli.proc` keeps the same posture on the write side.
    """
    base = (start or Path.cwd()).resolve()
    marker = harness.config_dir if harness else None
    for candidate in (base, *base.parents):
        if (candidate / ".git").exists():
            return candidate
        if marker and (candidate / marker).is_dir():
            return candidate
    return base


def artifact_path(host: Host, art: Artifact, mode: Mode, root: Path) -> Path:
    """Where ``art`` lives for ``mode``: under ``$HOME`` or under ``root``."""
    base = global_base() if mode == "global" else root
    return base / host.harness.relative_path(art.kind, art.name)


def occupied(path: Path) -> bool:
    """True when something sits at ``path``, a dangling symlink included."""
    return path.is_symlink() or path.exists()


def read_plain(path: Path) -> str | None:
    """The text of a readable plain file, else ``None``. Never raises."""
    if path.is_symlink() or not path.is_file():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def is_generated(path: Path, host: Host) -> bool:
    """True only for a plain file that ``host`` generated."""
    text = read_plain(path)
    return text is not None and is_stamped(text, host)


# -- checking ----------------------------------------------------------------


def classify(path: Path, host: Host, expected: str, mode: Mode) -> tuple[Status, str]:
    """Judge what sits at ``path`` against ``expected``, the current render.

    A file that cannot be read (bad permissions, not UTF-8) folds into
    ``foreign``, and the CLI points at ``--force``. That is honest only because
    every write here is wholesale: ``--force`` genuinely fixes it. The rule the
    status set obeys is that **a status must not imply a remedy the tool cannot
    perform** — so an artifact kind that is *edited in place* rather than
    rewritten (appending or amending one line of a file the host does not own)
    needs its own ``unreadable`` status from the start. There, an installer that
    cannot read the file refuses to write it, and both ``foreign`` and
    ``missing`` would send the user in a circle.
    """
    if not occupied(path):
        return "missing", "not installed"
    if path.is_symlink():
        return "foreign", "a symlink, not a plain file"
    if path.is_dir():
        return "foreign", "a directory, not a file"
    text = read_plain(path)
    if text is None:
        return "foreign", "unreadable or not UTF-8"
    if not is_stamped(text, host):
        other = stamped_by(text)
        if other:
            return "foreign", f"generated by {other}, not {host.dist}"
        return "foreign", "no stamp; hand-written or from an older release"
    if mask_versions(text, host) == mask_versions(expected, host):
        return "ok", ""
    recorded = stamped_mode(text, host)
    if recorded is not None and recorded != mode:
        return "drifted", f"rendered for mode={recorded}, installed where mode={mode}"
    return "drifted", "content differs from the current render"


def check_artifact(host: Host, art: Artifact, mode: Mode, root: Path) -> Check:
    """The drift verdict for ``art`` at its ``mode`` location.

    A copy whose content matches its render is still ``stale`` when a resolved
    global install has superseded it and the harness loads both — see
    :func:`stale_local`. Content correctness is not the question there; the
    file's continued existence is.
    """
    path = artifact_path(host, art, mode, root)
    status, reason = classify(path, host, render(host, art, mode), mode)
    if status == "ok" and stale_local(host, art, mode, root):
        return Check(
            art,
            mode,
            path,
            "stale",
            "superseded by the global copy but still loaded; remove it",
        )
    return Check(art, mode, path, status, reason)


def check(host: Host, root: Path, mode: Mode | None = None) -> list[Check]:
    """Drift for every artifact.

    With ``mode`` given, each artifact is judged at that one location. Without
    it, every occupied location is judged (global first), because the harness
    loads rules and agents from both at once and a stale copy at either is
    real drift. An artifact present at neither location reports ``missing``
    once, against its global path.
    """
    results: list[Check] = []
    for art in host.artifacts:
        if mode is not None:
            results.append(check_artifact(host, art, mode, root))
            continue
        found = [
            check_artifact(host, art, m, root)
            for m in MODES
            if occupied(artifact_path(host, art, m, root))
        ]
        results.extend(found or [check_artifact(host, art, "global", root)])
    return results


def installed_mode(host: Host, root: Path) -> Mode | None:
    """The mode an existing install resolves to, global first, or ``None``.

    Used to render printed bodies with the prefix the installed stub uses, so
    what the model reads agrees with the commands it was told to run. Skills
    decide it whenever the host ships any, because the stub is what carries
    those commands; a host that ships none falls back to its other artifacts so
    the answer stays grounded in what is actually on disk.

    ``None`` means *nothing is installed* and is deliberately not folded into a
    default here: callers that need a mode to print with substitute ``global``
    themselves, while callers asking "has this repo been pinned to global?"
    need the difference.
    """
    for art in host.skills or host.artifacts:
        for mode in MODES:
            if occupied(artifact_path(host, art, mode, root)):
                return mode
    return None


def stale_local(host: Host, art: Artifact, mode: Mode, root: Path) -> bool:
    """True when a local copy of ``art`` is live leftovers from before a switch.

    A resolved global install serves this repo, yet a per-repo copy of a kind
    the harness loads from *both* bases is still sitting there — so it is in
    context right now, matching content or not. The remedy is to remove it, not
    to regenerate it.

    Three guards keep the verdict honest:

    * Only ``local`` rows. The asymmetry is deliberate: a *global* copy present
      during a local install is shared infrastructure serving every other
      repository, never this repo's leftover, and is never flagged.
    * Only a genuinely resolved global install counts, so a local-only copy in
      a repo with no global install still reads ``ok``.
    * Only when the two paths differ, which they do not when the repo root is
      ``$HOME`` — there is one file there, not a leftover second one.
    """
    if mode != "local" or host.harness.shadows(art.kind):
        return False
    if installed_mode(host, root) != "global":
        return False
    return artifact_path(host, art, "local", root) != artifact_path(
        host, art, "global", root
    )


def shadowed_skills(host: Host, root: Path) -> list[Path]:
    """Local skill stubs that a global copy of the same skill shadows.

    Under Claude Code's precedence the global skill wins, so a per-repo stub
    with the same name is inert. Empty when the repo root is ``$HOME``, where
    the two paths coincide and there is really only one file.
    """
    out: list[Path] = []
    for skill in host.skills:
        glob = artifact_path(host, skill, "global", root)
        local = artifact_path(host, skill, "local", root)
        if glob != local and occupied(glob) and occupied(local):
            out.append(local)
    return out


# -- writing -----------------------------------------------------------------


def guard(host: Host, root: Path, mode: Mode, *, force: bool) -> None:
    """Refuse the install if any target is foreign and ``force`` is off."""
    if force:
        return
    for art in host.artifacts:
        path = artifact_path(host, art, mode, root)
        if occupied(path) and not is_generated(path, host):
            status, reason = classify(path, host, "", mode)
            raise ForeignArtifactError(
                path, reason if status == "foreign" else "foreign"
            )


def write_artifact(host: Host, art: Artifact, mode: Mode, root: Path) -> Path:
    """Write ``art``'s render for ``mode``, creating parents as needed.

    A symlink at the target, dangling or not, is replaced with a plain file
    rather than written through, so a write can never reach outside the tree
    it was aimed at.
    """
    path = artifact_path(host, art, mode, root)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        path.unlink()
    path.write_text(render(host, art, mode), encoding="utf-8")
    return path


def remove_stale_local(host: Host, root: Path) -> list[Path]:
    """Drop per-repo copies that a fresh global install supersedes.

    Only runs after a global install, never removes anything the host did not
    generate, and never touches a path that coincides with the global one.
    The reverse cleanup is deliberately absent: a local install never deletes
    the global copy that serves every other repository.
    """
    removed: list[Path] = []
    for art in host.artifacts:
        local = artifact_path(host, art, "local", root)
        if local == artifact_path(host, art, "global", root):
            continue
        if is_generated(local, host):
            local.unlink()
            removed.append(local)
    return removed


def install(
    host: Host, root: Path, mode: Mode, *, force: bool = False
) -> InstallReport:
    """Write every artifact for ``mode`` and run the host's follow-up hook.

    Raises :class:`ForeignArtifactError` before writing anything when a target
    is not ours and ``force`` is off.
    """
    guard(host, root, mode, force=force)
    written = tuple(write_artifact(host, art, mode, root) for art in host.artifacts)
    removed: tuple[Path, ...] = ()
    shadowed: tuple[Path, ...] = ()
    if mode == "global":
        removed = tuple(remove_stale_local(host, root))
    else:
        shadowed = tuple(shadowed_skills(host, root))
    report = InstallReport(host, mode, root, written, removed, shadowed)
    if host.after_install is not None:
        host.after_install(report)
    return report


def skill_stub_paths(host: Host, root: Path) -> list[tuple[Skill, Mode, Path]]:
    """Every skill stub location, for callers that narrate state."""
    return [
        (skill, mode, artifact_path(host, skill, mode, root))
        for skill in host.skills
        for mode in MODES
    ]
