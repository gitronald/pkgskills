"""Wire a host's commands into a repository's pre-commit hooks.

A host that ships a ``validate`` or ``index`` command wants it to run as a git
hook, and the mechanism is the same for every host: append a ``repo: local``
block naming the hooks to ``.pre-commit-config.yaml``, register each stage the
block uses with ``pre-commit install``, and report — without gating — whether
the hook is live in *this* clone. Only the hook declarations are host data.

Nothing here runs on the library's initiative. A host calls :func:`wire` from
its :attr:`~pkgskills.host.Host.after_install` and :func:`checks` from its
:attr:`~pkgskills.host.Host.extra_checks`; both shell out through
:func:`pkgskills.proc.run`, so an ambient ``GIT_DIR`` cannot aim the hook at
another repository.

Three rules the wiring keeps:

* **The entry is derived, never written by hand.** ``entry`` is the host's
  invocation for the install mode plus the hook's ``args``, so an entry can
  only be mode-correct.
* **Resync on a switch, leave alone otherwise.** An entry that names the
  *other* mode's invocation is rewritten only when the install is a genuine
  switch (:attr:`InstallReport.previous <pkgskills.artifacts.InstallReport.previous>`
  differs from the mode). A same-mode refresh leaves it, because the config is
  repo content a user may have set deliberately — a host's own dev repo keeps
  ``uv run <cli>`` while using a global stub, since the host is a local
  dependency there. An entry that names neither invocation is always left.
* **Report what is, apart from what an attempt did.** :class:`HookReport` is
  the write-time vocabulary; the rows :func:`checks` returns are read-only and
  use their own, per the rule on :class:`~pkgskills.host.ExtraCheck`.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Literal

from pkgskills.artifacts import InstallReport, occupied, printing_mode, read_plain
from pkgskills.host import ExtraCheck, Host, Mode
from pkgskills.proc import run

__all__ = [
    "CONFIG",
    "Activation",
    "Clone",
    "Hook",
    "HookReport",
    "HookState",
    "add_dependency",
    "checks",
    "hook_state",
    "hooks_dir",
    "precommit_command",
    "wire",
]

#: The pre-commit config, relative to the repository root.
CONFIG = Path(".pre-commit-config.yaml")

#: What registering a stage did. ``skipped`` is the caller's ``activate=False``;
#: ``no_git_repo`` has nowhere to register; ``hookspath_blocked`` is git's
#: ``core.hooksPath``, which makes ``pre-commit install`` refuse outright;
#: ``unavailable`` is a missing or failing ``pre-commit``.
Activation = Literal[
    "activated",
    "already_active",
    "skipped",
    "no_git_repo",
    "hookspath_blocked",
    "unavailable",
]

#: What ``install --check`` can say about a hook without touching anything.
#: ``missing`` is no entry in the config, the one state a plain reinstall
#: fixes; the rest are per-clone registration, which a correct consumer may
#: legitimately lack.
HookState = Literal["active", "unregistered", "missing", "no_git_repo", "blocked"]

# pre-commit's generated hook scripts carry its name; a hand-written script at
# the same path does not, and is not our hook.
_MARKER = "pre-commit"


@dataclass(frozen=True)
class Hook:
    """One hook the host wants in the consumer's pre-commit config.

    ``id`` is the pre-commit hook id and the token the wiring keys on; ``stage``
    the git hook it runs at (``pre-commit``, ``post-merge``, ...); ``args``
    what follows the host's invocation in ``entry``. The remaining fields pass
    through to the hook entry with pre-commit's own defaults: filenames are
    passed unless ``pass_filenames`` is False, which a whole-repo hook (an
    ``always_run`` one at ``post-merge``, say) sets explicitly; ``name``
    defaults to the id.
    """

    id: str
    stage: str = "pre-commit"
    args: tuple[str, ...] = ()
    name: str | None = None
    pass_filenames: bool = True
    always_run: bool = False
    files: str | None = None

    def entry(self, invocation: str) -> str:
        """The ``entry`` value for a host invoked as ``invocation``."""
        return " ".join((invocation, *self.args))

    def render(self, invocation: str) -> str:
        """The hook's YAML entry, indented for a ``repo: local`` block.

        ``name`` and ``files`` are single-quoted: a regex or a display name is
        free text that may carry ``: `` or `` #``, which an unquoted scalar
        would read as a mapping or a comment. The id and the entry are left
        bare, since both are matched as text elsewhere and neither is free-form.
        """
        lines = [
            f"      - id: {self.id}",
            f"        name: {_quote(self.name or self.id)}",
            f"        entry: {self.entry(invocation)}",
            "        language: system",
        ]
        if self.stage != "pre-commit":
            lines.append(f"        stages: [{self.stage}]")
        if self.files is not None:
            lines.append(f"        files: {_quote(self.files)}")
        if self.always_run:
            lines.append("        always_run: true")
        if not self.pass_filenames:
            lines.append("        pass_filenames: false")
        return "\n".join(lines) + "\n"


@dataclass(frozen=True)
class HookReport:
    """What :func:`wire` did: the config edits, and each stage's registration.

    ``unreadable`` means the config is there but could not be read, so it was
    left alone and no hook was added to it; registration is still attempted,
    since the entry may well be in the text that could not be read.
    """

    config: Path
    created: bool = False
    added: tuple[str, ...] = ()
    resynced: tuple[str, ...] = ()
    activation: Mapping[str, Activation] = field(
        default_factory=lambda: MappingProxyType(dict[str, Activation]())
    )
    unreadable: bool = False

    @property
    def changed(self) -> bool:
        """True when the config was created or edited."""
        return self.created or bool(self.added) or bool(self.resynced)


def precommit_command(host: Host, mode: Mode) -> tuple[str, ...]:
    """How ``pre-commit`` is invoked for ``mode``: bare, or through the local prefix.

    A local install runs everything through the host's ``local_prefix``, and
    ``pre-commit`` is a dev dependency there like the host itself. A global
    install has the host on ``PATH`` and expects ``pre-commit`` there too.
    """
    if mode == "global":
        return ("pre-commit",)
    return (*host.local_prefix.split(), "pre-commit")


def _quote(value: str) -> str:
    """``value`` as a single-quoted YAML scalar; only ``'`` needs doubling."""
    return "'" + value.replace("'", "''") + "'"


def _block(hooks: Sequence[Hook], invocation: str) -> str:
    return "  - repo: local\n    hooks:\n" + "\n".join(
        hook.render(invocation) for hook in hooks
    )


def _append(text: str, block: str) -> str:
    if text and not text.endswith("\n"):
        text += "\n"
    return text + block


def _bare(text: str) -> bool:
    """True when ``text`` has no content line: empty, blank, or comments only.

    Such a config has no ``repos:`` key for a block to hang under, so it is
    seeded like an absent one — appended to, since a comment is content.
    """
    return all(
        not line.strip() or line.lstrip().startswith("#") for line in text.splitlines()
    )


def _names(text: str, hook_id: str) -> bool:
    """True when ``text`` has a hook entry for ``hook_id``, as its own line.

    Anchored to the ``- id:`` line rather than a substring search, so an id
    that is a prefix of another (``x-index`` next to ``x-index-all``) is not
    mistaken for present.
    """
    pattern = rf"^\s*-\s*id:\s*{re.escape(hook_id)}\s*$"
    return re.search(pattern, text, re.MULTILINE) is not None


def _entry_line(hook: Hook, invocation: str) -> str:
    return f"        entry: {hook.entry(invocation)}\n"


def wire(
    report: InstallReport,
    hooks: Sequence[Hook],
    *,
    activate: bool = True,
    precommit: Sequence[str] | None = None,
) -> HookReport:
    """Put ``hooks`` in the config and register their stages.

    Appends only what is missing, as one ``repo: local`` block per call — a
    second block is valid pre-commit, and a text append needs no YAML parser
    and cannot disturb an entry already committed. A hook already in the
    config is keyed on its id, so a customized entry still counts as present.
    Its ``entry`` is resynced only when the install switched modes and the
    line names exactly the other mode's invocation.

    ``activate`` off writes the config and registers nothing. ``precommit``
    overrides how ``pre-commit`` is invoked; the default is
    :func:`precommit_command` for the install mode.
    """
    host, root, mode = report.host, report.root, report.mode
    invocation = host.invocation(mode)
    config = root / CONFIG
    text = read_plain(config)
    created = text is None and not occupied(config)
    # Occupied but unreadable: a symlink, a directory, bad permissions, or
    # bytes that are not UTF-8. Every edit below appends to or amends text
    # this function has read, so with none in hand there is no edit that
    # would not discard the rest of the file.
    unreadable = text is None and not created
    if text is None:
        text = "repos:\n"
    elif _bare(text):
        # Exists but holds nothing a block can hang under: seed the key.
        text = _append(text, "repos:\n")
    missing: list[Hook] = []
    if not unreadable:
        missing = [hook for hook in hooks if not _names(text, hook.id)]
    resynced: list[str] = []
    switched = report.previous is not None and report.previous != mode
    if switched and not unreadable:
        other = host.invocation("local" if mode == "global" else "global")
        for hook in hooks:
            if hook in missing:
                continue
            stale, fresh = _entry_line(hook, other), _entry_line(hook, invocation)
            if fresh not in text and stale in text:
                text = text.replace(stale, fresh)
                resynced.append(hook.id)
    if missing:
        text = _append(text, _block(missing, invocation))
    if created or missing or resynced:
        config.write_text(text, encoding="utf-8")
    command = tuple(precommit) if precommit else precommit_command(host, mode)
    # One look at the clone for every stage: the hooks directory and
    # core.hooksPath are per-repository, and each costs a git subprocess.
    clone = Clone.of(root)
    activation: dict[str, Activation] = {}
    for stage in dict.fromkeys(hook.stage for hook in hooks):
        activation[stage] = _activate(clone, root, stage, command, attempt=activate)
    return HookReport(
        config,
        created,
        tuple(hook.id for hook in missing),
        tuple(resynced),
        MappingProxyType(activation),
        unreadable,
    )


def add_dependency(root: Path, prefix: str = "uv") -> bool:
    """Add ``pre-commit`` as a dev dependency; ``True`` on success.

    Runs ``<prefix> add --dev pre-commit``, so the default is ``uv``.

    Kept apart from :func:`wire` because it edits the consumer's
    ``pyproject.toml``, which a default install should not do unasked. Best
    effort like the other shell-outs: a missing tool or a non-zero exit is
    ``False``, never an exception.
    """
    try:
        done = run(
            root, [*prefix.split(), "add", "--dev", "pre-commit"], capture_output=True
        )
    except FileNotFoundError:
        return False
    return done.returncode == 0


# -- registration ------------------------------------------------------------


def is_git_repo(root: Path) -> bool:
    """True for a working tree: ``.git`` is a directory or a worktree's pointer."""
    return (root / ".git").exists()


def _parsed_hooks_dir(root: Path) -> Path | None:
    """The hooks directory from ``.git`` alone, without consulting git.

    Handles a plain repo and a linked worktree, whose ``.git`` is a file of the
    form ``gitdir: <path>``. Ignores ``core.hooksPath``; that needs git.
    """
    git = root / ".git"
    if git.is_dir():
        return git / "hooks"
    if not git.is_file():
        return None
    pointer = (read_plain(git) or "").strip()
    if not pointer.startswith("gitdir:"):
        return None
    gitdir = Path(pointer[len("gitdir:") :].strip())
    if not gitdir.is_absolute():
        gitdir = root / gitdir
    return gitdir / "hooks"


def hooks_dir(root: Path) -> Path | None:
    """The directory git runs ``root``'s hooks from, or ``None`` outside a repo.

    Asks git (``rev-parse --git-path hooks``), which honors ``core.hooksPath``
    and resolves a worktree's git dir; a relative answer is joined onto
    ``root`` because the call runs there. Falls back to reading ``.git``
    directly when git is absent or refuses, so a synthetic ``.git`` still
    resolves.
    """
    try:
        done = run(
            root, ["git", "rev-parse", "--git-path", "hooks"], capture_output=True
        )
    except FileNotFoundError:
        return _parsed_hooks_dir(root)
    out = done.stdout.strip()
    if done.returncode != 0 or not out:
        return _parsed_hooks_dir(root)
    path = Path(out)
    return path if path.is_absolute() else root / path


def _registered(where: Path | None, stage: str) -> bool:
    text = read_plain(where / stage) if where is not None else None
    return text is not None and _MARKER in text


def registered(root: Path, stage: str) -> bool:
    """True when pre-commit's script for ``stage`` is in the effective hooks dir."""
    return _registered(hooks_dir(root), stage)


def hookspath_set(root: Path) -> bool:
    """True when ``core.hooksPath`` is set, so ``pre-commit install`` would refuse."""
    try:
        done = run(
            root, ["git", "config", "--get", "core.hooksPath"], capture_output=True
        )
    except FileNotFoundError:
        return False
    return done.returncode == 0 and bool(done.stdout.strip())


@dataclass(frozen=True)
class Clone:
    """What a clone says about hook registration, read once per call.

    The hooks directory and ``core.hooksPath`` are per-repository and each
    costs a git subprocess, so :func:`wire` and :func:`checks` take them once
    rather than once per stage or per hook.
    """

    is_repo: bool
    hooks: Path | None
    hookspath: bool

    @classmethod
    def of(cls, root: Path) -> Clone:
        return cls(is_git_repo(root), hooks_dir(root), hookspath_set(root))

    def registered(self, stage: str) -> bool:
        return _registered(self.hooks, stage)


def _activate(
    clone: Clone, root: Path, stage: str, command: Sequence[str], *, attempt: bool
) -> Activation:
    """Register ``stage`` in ``root``; never raises."""
    if clone.registered(stage):
        return "already_active"
    if not attempt:
        return "skipped"
    if not clone.is_repo:
        return "no_git_repo"
    if clone.hookspath:
        return "hookspath_blocked"
    try:
        done = run(
            root, [*command, "install", "--hook-type", stage], capture_output=True
        )
    except FileNotFoundError:
        return "unavailable"
    return "activated" if done.returncode == 0 else "unavailable"


# -- checking ----------------------------------------------------------------


def hook_state(
    root: Path, hook: Hook, *, clone: Clone | None = None, config: str | None = None
) -> HookState:
    """Read-only: will ``hook`` fire in this clone?

    The config is read before the registration, because a registered stage
    says only that pre-commit itself is wired in — a repo using it for other
    hooks satisfies that with no entry for ours at all. An unreadable config
    is one that does not name the hook. ``clone`` and ``config`` let a caller
    judging several hooks read the clone and the config once.
    """
    text = (read_plain(root / CONFIG) or "") if config is None else config
    if not _names(text, hook.id):
        return "missing"
    if clone is None:
        clone = Clone.of(root)
    if clone.registered(hook.stage):
        return "active"
    if not clone.is_repo:
        return "no_git_repo"
    if clone.hookspath:
        return "blocked"
    return "unregistered"


def checks(
    host: Host,
    root: Path,
    mode: Mode | None,
    hooks: Sequence[Hook],
    *,
    precommit: Sequence[str] | None = None,
) -> list[ExtraCheck]:
    """One non-gating :class:`~pkgskills.host.ExtraCheck` row per hook.

    Registration is per-clone state a fresh clone lacks, so no row gates; each
    carries a note naming the command that fixes it. ``mode`` picks which
    install command and ``pre-commit`` invocation the notes name; ``None``
    falls back to the host's default mode.
    """
    resolved = mode or printing_mode(host, root)
    command = " ".join(precommit or precommit_command(host, resolved))
    rows: list[ExtraCheck] = []
    clone = Clone.of(root) if hooks else None
    config = read_plain(root / CONFIG) or ""
    for hook in hooks:
        state = hook_state(root, hook, clone=clone, config=config)
        note = ""
        if state == "missing":
            note = (
                f"no {hook.id} entry in {CONFIG}; "
                f"run `{host.install_command(resolved)}`"
            )
        elif state == "unregistered":
            note = (
                f"{hook.id} is not registered in this clone, so it never fires; "
                f"run `{command} install --hook-type {hook.stage}`"
            )
        elif state == "no_git_repo":
            note = f"{hook.id} has no git repository to register in"
        elif state == "blocked":
            note = (
                f"{hook.id} is not registered: git's core.hooksPath is set, so "
                f"`{command} install` refuses; unset it with "
                "`git config --unset-all core.hooksPath`, then register it"
            )
        rows.append(ExtraCheck(f"hook {hook.id}", state, gates=False, note=note))
    return rows
