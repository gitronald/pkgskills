"""Materialize, locate, and drift-check generated artifacts.

Two install modes, both first-class:

* **global**: one copy under ``$HOME`` serves every repository; the host CLI
  is on ``PATH`` and invoked bare.
* **local**: the copy lives under the repository root and the CLI is invoked
  through ``uv run`` (or the host's ``local_prefix``).

A file's mode is the one its location implies. A copy rendered for one mode
and carried to the other location reads as drifted, because the commands
embedded in it are wrong where it sits.

Which of the two a given host uses is the host's to declare: everything here
walks :attr:`Host.modes <pkgskills.host.Host.modes>` rather than both, so a host that
supports one mode is never checked at, or written to, the other's location.

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

from pkgskills.harness import Harness, Kind
from pkgskills.host import Artifact, Host, Line, Mode, Skill
from pkgskills.rendering import render
from pkgskills.stamp import is_stamped, mask_versions, stamped_by, stamped_mode

Status = Literal["ok", "drifted", "stale", "missing", "foreign"]

#: The verdicts for a :class:`~pkgskills.host.Line`, a file edited in place.
#: ``unreadable`` is its own status because ``--force`` cannot fix it: the
#: installer refuses to rewrite a file whose other lines it cannot see, so
#: both ``foreign`` and ``missing`` would promise a remedy it will not perform.
LineStatus = Literal["ok", "drifted", "missing", "unreadable"]


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
class LineCheck:
    """The verdict for one declared line, with the line found in its place.

    ``found`` is the whitespace-normalized line that names the key when the
    status is ``drifted``, so a caller can say what the file grants instead of
    only that it differs.
    """

    line: Line
    path: Path
    status: LineStatus
    found: str = ""

    @property
    def ok(self) -> bool:
        return self.status == "ok"


@dataclass(frozen=True)
class LineWrite:
    """What an install did about one line: the verdict before, and whether it wrote."""

    check: LineCheck
    written: bool


@dataclass(frozen=True)
class InstallReport:
    """What an install did, for the CLI to narrate and hooks to act on.

    ``previous`` is the mode an existing install resolved to before this one
    wrote anything, or ``None`` on a first install. A hook that keeps repo
    content in step with the mode — a pre-commit entry, say — needs it to tell
    a genuine switch from a same-mode refresh, since afterwards the fresh
    files always read as the requested mode.

    ``force`` carries the user's explicit consent to overwrite through to
    :attr:`Host.after_install <pkgskills.host.Host.after_install>`. Every
    artifact write is wholesale, so the flag is already spent by the time a
    hook runs; it is passed on for a hook that edits a file in place, which
    otherwise has no way to tell a line it may replace from one it must leave
    alone. The declared :attr:`~pkgskills.host.Host.lines` honor it the same
    way, and ``lines`` records what happened to each.

    ``renamed`` lists the stamped files removed from an artifact's previous
    names; ``leftover`` lists the unstamped files found there and left alone.
    """

    host: Host
    mode: Mode
    root: Path
    written: tuple[Path, ...] = field(default_factory=tuple)
    removed: tuple[Path, ...] = field(default_factory=tuple)
    shadowed: tuple[Path, ...] = field(default_factory=tuple)
    force: bool = False
    previous: Mode | None = None
    lines: tuple[LineWrite, ...] = field(default_factory=tuple)
    renamed: tuple[Path, ...] = field(default_factory=tuple)
    leftover: tuple[Path, ...] = field(default_factory=tuple)


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
    :mod:`pkgskills.proc` keeps the same posture on the write side.
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


def previous_paths(
    host: Host, art: Artifact, mode: Mode, root: Path
) -> list[tuple[str, Path]]:
    """Where ``art`` used to live for ``mode``, one path per previous name."""
    base = global_base() if mode == "global" else root
    return [
        (name, base / host.harness.relative_path(art.kind, name))
        for name in art.previous_names
    ]


def line_path(line: Line, root: Path) -> Path:
    """Where ``line``'s file lives: always under ``root``, whatever the mode."""
    return root / line.path


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
    perform** — which is why a :class:`~pkgskills.host.Line`, edited in place
    rather than rewritten, has its own :data:`LineStatus` with ``unreadable``
    in it. There, an installer that cannot read the file refuses to write it,
    and both ``foreign`` and ``missing`` would send the user in a circle.
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
        if other == host.dist:
            # Only that the stamp names this dist and is not one pkgskills
            # wrote. Which of the two it is -- a release predating adoption, or
            # a stamp pkgskills wrote that something later mangled -- the line
            # no longer records, so the reason claims neither. The remedy is
            # the same either way, and the CLI appends it.
            return (
                "foreign",
                f"a {host.dist} stamp pkgskills did not write; hand-edited, or "
                f"from a release before {host.dist} adopted pkgskills",
            )
        if other:
            return "foreign", f"generated by {other}, not {host.dist}"
        return "foreign", "no stamp; hand-written or from an older release"
    if mask_versions(text, host) == mask_versions(expected, host):
        return "ok", ""
    recorded = stamped_mode(text, host)
    if recorded is not None and recorded != mode:
        return "drifted", f"rendered for mode={recorded}, installed where mode={mode}"
    return "drifted", "content differs from the current render"


def check_artifact(
    host: Host,
    art: Artifact,
    mode: Mode,
    root: Path,
    *,
    installed: Mode | None | Literal["auto"] = "auto",
) -> Check:
    """The drift verdict for ``art`` at its ``mode`` location.

    A copy is ``stale`` when a resolved global install has superseded it and the
    harness loads both — see :func:`stale_local`. Content correctness is not the
    question there; the file's continued existence is, so the verdict outranks
    both ``ok`` *and* ``drifted``. Rewriting a drifted leftover would only
    recreate the file the remedy asks the user to remove.

    ``installed`` is :func:`installed_mode`'s answer, which is one fact per
    check run rather than per row; :func:`check` computes it once and passes it
    down. The default re-derives it, so a lone call still works.
    """
    path = artifact_path(host, art, mode, root)
    status, reason = classify(path, host, render(host, art, mode), mode)
    if status in ("ok", "drifted") and stale_local(
        host, art, mode, root, installed=installed
    ):
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
    it, every occupied location the host supports is judged, in the host's
    declared mode order (global first by default), because the harness loads
    rules and agents from both at once and a stale
    copy at either is real drift. An artifact present at neither location
    reports ``missing`` once, against its default mode's path.
    """
    # One fact for the whole run: which mode an existing install resolves to.
    # Re-deriving it per row would re-walk the filesystem for every artifact.
    installed = installed_mode(host, root)
    results: list[Check] = []
    for art in host.artifacts:
        modes = (mode,) if mode is not None else host.modes
        if mode is None:
            found = [
                check_artifact(host, art, m, root, installed=installed)
                for m in modes
                if occupied(artifact_path(host, art, m, root))
            ]
            results.extend(
                found
                or [
                    check_artifact(
                        host, art, host.default_mode, root, installed=installed
                    )
                ]
            )
        else:
            results.append(check_artifact(host, art, mode, root, installed=installed))
        # A stamped file at a name the artifact no longer installs under is
        # still loaded by the harness, so it is real drift. Only a stamped one:
        # an unstamped file there is somebody else's and earns no row.
        for m in modes:
            for name, path in previous_paths(host, art, m, root):
                if is_generated(path, host):
                    results.append(
                        Check(
                            art,
                            m,
                            path,
                            "stale",
                            f"installed under the previous name {name!r}; remove it",
                        )
                    )
    return results


def leftover_previous(host: Host, mode: Mode, root: Path) -> list[Path]:
    """Unstamped files sitting at an artifact's previous names for ``mode``.

    Never removed, since nothing says they are ours; surfaced so the user can
    decide. Only plain files count — a directory or symlink at an old skill
    path is not a leftover rule that will be auto-loaded.
    """
    found: list[Path] = []
    for art in host.artifacts:
        for _, path in previous_paths(host, art, mode, root):
            text = read_plain(path)
            if text is not None and not is_stamped(text, host):
                found.append(path)
    return found


# -- lines -------------------------------------------------------------------


def _find_line(text: str, key: str) -> tuple[int, str] | None:
    """The last line of ``text`` whose first field is ``key``, normalized.

    Returns ``(line number, whitespace-normalized line)``. Last rather than
    first because that is the one git obeys for attributes: a file carrying
    both ``merge=union`` and a later ``merge=ours`` for the same pattern is a
    repo running ``ours``, and reading the first match would call it ``ok``.
    Normalizing whitespace keeps a padded but equivalent line from reading as
    drift. Blank and ``#`` lines are skipped. Patterns are compared as written,
    so a differently spelled pattern for the same file reads as absent — the
    safe direction, since the line then appended is the last match and wins.
    """
    found: tuple[int, str] | None = None
    for number, raw in enumerate(text.splitlines()):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        fields = stripped.split()
        if fields[0] == key:
            found = (number, " ".join(fields))
    return found


def _read_line(line: Line, root: Path) -> tuple[LineCheck, str]:
    """The verdict for ``line`` and the text it was read from, in one read.

    The text is ``""`` when the file is absent or unreadable, so a caller
    that goes on to edit has the same bytes the verdict came from.
    """
    path = line_path(line, root)
    if not occupied(path):
        return LineCheck(line, path, "missing"), ""
    text = read_plain(path)
    if text is None:
        return LineCheck(line, path, "unreadable"), ""
    found = _find_line(text, line.key)
    if found is None:
        return LineCheck(line, path, "missing"), text
    number, normalized = found
    if normalized == line.text:
        return LineCheck(line, path, "ok"), text
    return LineCheck(line, path, "drifted", normalized), text


def check_line(line: Line, root: Path) -> LineCheck:
    """The :data:`LineStatus` verdict for ``line`` in ``root``."""
    return _read_line(line, root)[0]


def check_lines(host: Host, root: Path) -> list[LineCheck]:
    """The verdict for every line the host declares."""
    return [check_line(line, root) for line in host.lines]


def write_line(line: Line, root: Path, *, force: bool = False) -> LineWrite:
    """Put ``line`` in its file: append when absent, rewrite in place under ``force``.

    Other lines are preserved — the line is appended or one line amended,
    never the file rewritten from scratch. A line naming the key with another
    value is left alone unless ``force`` is set, since the file is repo
    content a user may have set deliberately. An unreadable file is left alone
    ``force`` or not: with no text in hand there is no edit that would not
    discard the rest of the file.
    """
    # One read: the edit below works on the very text the verdict came from.
    before, text = _read_line(line, root)
    if before.status in ("ok", "unreadable"):
        return LineWrite(before, False)
    path = before.path
    if before.status == "missing":
        # Absent, or a readable file with no line for the key: anything else
        # was called `unreadable` above.
        if text and not text.endswith("\n"):
            text += "\n"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text + line.text + "\n", encoding="utf-8")
        return LineWrite(before, True)
    if not force:
        return LineWrite(before, False)
    found = _find_line(text, line.key)
    assert found is not None  # `drifted` means this same text has the line
    number = found[0]
    lines = text.splitlines(keepends=True)
    ends = "\n" if lines[number].endswith("\n") else ""
    lines[number] = line.text + ends
    path.write_text("".join(lines), encoding="utf-8")
    return LineWrite(before, True)


def write_lines(host: Host, root: Path, *, force: bool = False) -> list[LineWrite]:
    """:func:`write_line` for every line the host declares, in order."""
    return [write_line(line, root, force=force) for line in host.lines]


def installed_mode(host: Host, root: Path) -> Mode | None:
    """The mode an existing install resolves to, or ``None``.

    Modes are tried in the host's declared order, so the host's preference
    decides which of two coexisting installs is the one being used.

    Used to render printed bodies with the prefix the installed stub uses, so
    what the model reads agrees with the commands it was told to run. Skills
    decide it whenever the host ships any, because the stub is what carries
    those commands; a host that ships none falls back to its other artifacts so
    the answer stays grounded in what is actually on disk.

    ``None`` means *nothing is installed* and is deliberately not folded into a
    default here: callers that need a mode to print with substitute the host's
    :attr:`~pkgskills.host.Host.default_mode` themselves, while callers asking "has
    this repo been pinned to global?" need the difference.
    """
    for art in host.skills or host.artifacts:
        for mode in host.modes:
            if occupied(artifact_path(host, art, mode, root)):
                return mode
    return None


def printing_mode(host: Host, root: Path) -> Mode:
    """The mode a *printed* body should render ``{cli}`` for.

    :func:`installed_mode` when anything is installed, the host's
    :attr:`~pkgskills.host.Host.default_mode` when nothing is — which is the whole
    of the "which prefix do I print?" decision, exported because a host that
    keeps a print command of its own has to make it the same way ``skill`` and
    ``doc`` do or the commands it prints will not run.
    """
    return installed_mode(host, root) or host.default_mode


def stale_local(
    host: Host,
    art: Artifact,
    mode: Mode,
    root: Path,
    *,
    installed: Mode | None | Literal["auto"] = "auto",
) -> bool:
    """True when a local copy of ``art`` is live leftovers from before a switch.

    A resolved global install serves this repo, yet a per-repo copy of a kind
    the harness loads from *both* bases is still sitting there — so it is in
    context right now, matching content or not. The remedy is to remove it, not
    to regenerate it.

    Three guards keep the verdict honest:

    * Only ``local`` rows, and only for a host that has a global mode at all —
      a local-only host can have nothing supersede its per-repo copy. The
      asymmetry is deliberate: a *global* copy present during a local install
      is shared infrastructure serving every other repository, never this
      repo's leftover, and is never flagged.
    * Only a genuinely resolved global install counts, so a local-only copy in
      a repo with no global install still reads ``ok``.
    * Only when the two paths differ, which they do not when the repo root is
      ``$HOME`` — there is one file there, not a leftover second one.

    ``installed`` lets a caller judging many artifacts hand in
    :func:`installed_mode`'s answer instead of paying for it once per row.
    """
    if mode != "local" or host.harness.shadows(art.kind):
        return False
    if not host.supports_mode("global"):
        return False
    resolved = installed_mode(host, root) if installed == "auto" else installed
    if resolved != "global":
        return False
    return artifact_path(host, art, "local", root) != artifact_path(
        host, art, "global", root
    )


def shadowed_skills(host: Host, root: Path) -> list[Path]:
    """Local skill stubs that a global copy of the same skill shadows.

    Under Claude Code's precedence the global skill wins, so a per-repo stub
    with the same name is inert. Empty when the repo root is ``$HOME``, where
    the two paths coincide and there is really only one file, and empty for a
    host with no global mode, which never puts a stub there to shadow with.
    """
    if not host.supports_mode("global"):
        return []
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


def remove_previous(host: Host, mode: Mode, root: Path) -> list[Path]:
    """Drop the stamped files at every artifact's previous names for ``mode``.

    The same test :func:`remove_stale_local` applies: only a plain file this
    host generated is removed, so a hand-written file at an old name — or
    another package's — is never touched. A skill's directory is removed with
    its stub when nothing else is in it; a directory that still holds
    something is left as it is.
    """
    removed: list[Path] = []
    current = {artifact_path(host, art, mode, root) for art in host.artifacts}
    for art in host.artifacts:
        for _, path in previous_paths(host, art, mode, root):
            # Guarded by validate, but the cost of a second check is nothing
            # next to deleting a file that was just written.
            if path in current or not is_generated(path, host):
                continue
            path.unlink()
            removed.append(path)
            if art.kind is Kind.SKILL:
                try:
                    path.parent.rmdir()
                except OSError:
                    pass
    return removed


def install(
    host: Host, root: Path, mode: Mode, *, force: bool = False
) -> InstallReport:
    """Write every artifact for ``mode`` and run the host's follow-up hook.

    After the artifacts: the declared lines go into their files under
    ``root``, and the stamped files at any previous names are removed.

    Raises :class:`ForeignArtifactError` before writing anything when a target
    is not ours and ``force`` is off, and ``ValueError`` when ``mode`` is not
    one the host supports — a local-only host must not be written under
    ``$HOME`` by a caller that bypassed the CLI's own check.
    """
    if not host.supports_mode(mode):
        raise ValueError(
            f"{host.dist} does not install in {mode} mode; "
            f"it supports: {', '.join(host.modes)}"
        )
    guard(host, root, mode, force=force)
    # Resolved before the first write, since afterwards the fresh files always
    # read as the requested mode.
    previous = installed_mode(host, root)
    written = tuple(write_artifact(host, art, mode, root) for art in host.artifacts)
    removed: tuple[Path, ...] = ()
    shadowed: tuple[Path, ...] = ()
    if mode == "global":
        removed = tuple(remove_stale_local(host, root))
    else:
        shadowed = tuple(shadowed_skills(host, root))
    lines = tuple(write_lines(host, root, force=force))
    renamed = tuple(remove_previous(host, mode, root))
    leftover = tuple(leftover_previous(host, mode, root))
    report = InstallReport(
        host,
        mode,
        root,
        written,
        removed,
        shadowed,
        force,
        previous,
        lines,
        renamed,
        leftover,
    )
    if host.after_install is not None:
        host.after_install(report)
    return report


def skill_stub_paths(host: Host, root: Path) -> list[tuple[Skill, Mode, Path]]:
    """Every skill stub location, for callers that narrate state."""
    return [
        (skill, mode, artifact_path(host, skill, mode, root))
        for skill in host.skills
        for mode in host.modes
    ]
