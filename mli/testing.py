"""Helpers for host test suites.

Everything ``mli`` does is relative to two roots, the home directory and the
repository root, and both are discovered from the environment. Tests that
forget to pin them read and write the developer's real ``~/.claude`` tree.
``sandbox`` pins both in one call, and ``mli_sandbox`` is the same as a pytest
fixture for suites that import it into their ``conftest``.

``wheel_files`` builds a real wheel in-process, because an editable install
resolves package data straight to the checkout and passes whether or not the
build ships it.

``prompt_commands`` and ``assert_prompt_commands`` close the loop the whole
pattern exists for: prose about a CLI goes stale. ``mli`` renders ``{cli}``
but nothing otherwise checks that what follows it is a command the host
actually has.
"""

from __future__ import annotations

import os
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from mli.harness import Kind
from mli.host import CLI_TOKEN, Host, Skill

if TYPE_CHECKING:
    import pytest
    import typer


@dataclass(frozen=True)
class Sandbox:
    """A pinned home directory and repository root."""

    home: Path
    repo: Path


def sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Sandbox:
    """Pin ``$HOME`` and the working directory to fresh directories under ``tmp_path``.

    The repo gets a ``.git`` marker so root discovery stops there.
    """
    home = tmp_path / "home"
    repo = tmp_path / "repo"
    home.mkdir()
    repo.mkdir()
    (repo / ".git").mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.chdir(repo)
    return Sandbox(home=home, repo=repo)


def wheel_files(project_root: Path, out_dir: Path) -> set[str]:
    """The paths inside a wheel built from ``project_root`` with hatchling."""
    try:
        from hatchling.build import build_wheel
    except ImportError as exc:  # pragma: no cover - dev dependency
        raise RuntimeError("wheel_files needs hatchling installed") from exc
    out_dir.mkdir(parents=True, exist_ok=True)
    cwd = Path.cwd()
    os.chdir(project_root)
    try:
        name = build_wheel(str(out_dir))
    finally:
        os.chdir(cwd)
    with zipfile.ZipFile(out_dir / name) as wheel:
        return set(wheel.namelist())


# -- commands a prompt names ------------------------------------------------

#: Commands whose argument names something the *host* declares rather than a
#: further subcommand. ``{cli} doc audit/severity`` and ``{cli} skill tidy``
#: are the mentions most likely to go stale, and a scanner that stopped at the
#: first path-shaped token would check neither.
DECLARING = ("skill", "doc", "rule", "agent")

# Markdown punctuation a mention picks up from the prose around it. Angle
# brackets are deliberately absent: `<id>` has to stay recognizable as a
# placeholder so the walk stops there instead of resolving it.
_TRIM = "`'\"()[]{},.;:!?*"
_COMMAND = re.compile(r"^[a-z][a-z0-9-]*$")
_PLACEHOLDER = re.compile(r"^<.+>$")
_CODE_SPAN = re.compile(r"`([^`]*)`")
_FENCE = "```"


@dataclass(frozen=True)
class PromptCommand:
    """One ``{cli} ...`` mention found in a prompt the host ships.

    ``tokens`` is the command path — every token up to the first that looks
    like an argument. ``argument`` is filled only for the commands in
    :data:`DECLARING`, whose argument is a declared name and therefore
    checkable too.
    """

    source: str
    line: int
    tokens: tuple[str, ...]
    argument: str | None = None

    @property
    def text(self) -> str:
        """The mention as it would be written, placeholder included."""
        parts = [CLI_TOKEN, *self.tokens]
        if self.argument is not None:
            parts.append(self.argument)
        return " ".join(parts)


def _clean(token: str) -> str:
    return token.strip(_TRIM)


def _mention(tokens: list[str]) -> tuple[tuple[str, ...], str | None] | None:
    """The command path and declared argument in the tokens after ``{cli}``.

    ``None`` when nothing command-shaped follows the token at all, as in a
    line that ends on ``{cli}`` or hands it straight to a path.
    """
    path: list[str] = []
    argument: str | None = None
    for i, token in enumerate(tokens):
        if not path and token in DECLARING:
            path.append(token)
            nxt = tokens[i + 1] if i + 1 < len(tokens) else ""
            if nxt and not nxt.startswith("-") and not _PLACEHOLDER.match(nxt):
                argument = nxt
            break
        if not _COMMAND.match(token):
            break
        path.append(token)
    return (tuple(path), argument) if path else None


def _sources(host: Host) -> list[str]:
    """Every prompt the host ships, in declaration order, docs last."""
    out: list[str] = []
    for art in host.artifacts:
        out.extend(art.sources if isinstance(art, Skill) else [art.source])
    out.extend(doc.source for doc in host.docs)
    return out


def _after_token(text: str) -> list[str]:
    """The remainder of ``text`` after each ``{cli}`` it contains."""
    out: list[str] = []
    at = text.find(CLI_TOKEN)
    while at != -1:
        out.append(text[at + len(CLI_TOKEN) :])
        at = text.find(CLI_TOKEN, at + len(CLI_TOKEN))
    return out


def _command_texts(line: str, *, fenced: bool) -> list[str]:
    """The text after each ``{cli}`` on ``line`` that is written as a command.

    Inside a fenced block the whole line is code. Outside one, only a code
    span counts: a body that mentions the bare token in prose ("it uses
    ``{cli}`` like any other body") is talking *about* the placeholder, and
    reading the next words as a command path invents a command to fail on.
    """
    if fenced:
        return _after_token(line)
    out: list[str] = []
    for span in _CODE_SPAN.finditer(line):
        out.extend(_after_token(span.group(1)))
    return out


def prompt_commands(host: Host) -> list[PromptCommand]:
    """Every ``{cli} ...`` mention in the skills, docs, rules, and agents.

    Scanning is by declaration, not by ``render_cli``: a body that carries the
    token without opting into substitution has a problem of its own, and one
    that opts in has its commands checked either way.
    """
    found: list[PromptCommand] = []
    for source in _sources(host):
        fenced = False
        for lineno, line in enumerate(host.read(source).splitlines(), start=1):
            if line.lstrip().startswith(_FENCE):
                fenced = not fenced
                continue
            for rest in _command_texts(line, fenced=fenced):
                mention = _mention([_clean(tok) for tok in rest.split()])
                if mention is None:
                    continue
                tokens, argument = mention
                found.append(
                    PromptCommand(
                        source=source, line=lineno, tokens=tokens, argument=argument
                    )
                )
    return found


def _declared_names(host: Host, command: str) -> tuple[str, ...]:
    """The names ``command`` accepts, drawn from the host's declarations."""
    if command == "skill":
        return tuple(host.skill_sources())
    if command == "doc":
        return tuple(doc.name for doc in host.docs)
    return tuple(art.name for art in host.of_kind(Kind(command)))


def _unresolved(host: Host, root: object, cmd: PromptCommand) -> str | None:
    """Why ``cmd`` names nothing real, or ``None`` when it resolves."""
    node = root
    for i, token in enumerate(cmd.tokens):
        commands = getattr(node, "commands", None)
        if not isinstance(commands, dict):
            # A leaf command, so whatever follows it is an argument rather
            # than a subcommand. The scanner cannot tell the two apart —
            # `{cli} close fix-typo` is tokens the same shape as a command
            # path — and only the app knows where the path ends.
            break
        if token not in commands:
            return f"no such command {' '.join(cmd.tokens[: i + 1])!r}"
        node = commands[token]
    if cmd.argument is not None:
        names = _declared_names(host, cmd.tokens[0])
        if cmd.argument not in names:
            declared = ", ".join(names) or "none"
            return (
                f"no {cmd.tokens[0]} {cmd.argument!r} is declared; "
                f"the host declares: {declared}"
            )
    return None


def assert_prompt_commands(host: Host, app: typer.Typer) -> None:
    """Fail unless every command a prompt names exists on ``app``.

    Each mention's command path is resolved against the typer app, and the
    argument to ``skill``, ``doc``, ``rule``, or ``agent`` against the host's
    own declarations. The shared grammar's commands resolve like any other,
    since ``register`` mounted them on the same app. Resolution stops at the
    first leaf command, so a body free to write a real argument
    (``{cli} close fix-typo``) rather than a placeholder still passes.
    """
    from typer.main import get_command

    root = get_command(app)
    failures = [
        f"  {cmd.source}:{cmd.line}: {cmd.text} -- {why}"
        for cmd in prompt_commands(host)
        if (why := _unresolved(host, root, cmd)) is not None
    ]
    if failures:
        raise AssertionError(
            f"{host.dist} prompts name commands that do not exist:\n"
            + "\n".join(failures)
        )


def __getattr__(name: str) -> object:
    # The fixture is created on first access so importing this module never
    # requires pytest.
    if name == "mli_sandbox":
        import pytest as _pytest

        @_pytest.fixture
        def mli_sandbox(tmp_path: Path, monkeypatch: _pytest.MonkeyPatch) -> Sandbox:
            return sandbox(tmp_path, monkeypatch)

        return mli_sandbox
    raise AttributeError(name)
