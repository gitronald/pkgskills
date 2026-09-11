"""The host declaration: what a package ships and how its CLI is invoked.

A *host* is a package that bundles prompts as package data and exposes them
through its own CLI. It declares itself once, as a :class:`Host`, and mounts
the shared commands with :func:`mli.cli.register`. Everything ``mli`` renders,
writes, or checks derives from that declaration plus the installed package
version, so nothing about the host is restated anywhere else.

Artifacts come in three kinds. A :class:`Skill` is materialized as a thin
*stub* that tells the model to print the real instructions with
``<cli> skill <name>``; a skill with several sources becomes a dispatcher whose
subcommands are the source names. A :class:`Rule` and an :class:`Agent`
are materialized as stamped *copies*, because the harness reads their full
text off disk with no model in the loop.

A :class:`Doc` is the fourth declared thing and the one that is *not* an
artifact: it is printed by ``<cli> doc <name>`` and never written to disk. It
exists because a skill body that says "read ``references/x.md`` first" has
nowhere to read it from once the body is printed from a package — there is no
skill directory next to the stub. Docs therefore live on :attr:`Host.docs`
rather than in :attr:`Host.artifacts`, since an artifact here is something
materialized at a location per mode and a doc has neither.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from importlib import metadata, resources
from pathlib import PurePosixPath
from types import MappingProxyType
from typing import TYPE_CHECKING, Literal

from mli.harness import CLAUDE_CODE, Harness, Kind
from mli.permissions import LEVELS, Level
from mli.spec import SPEC, SpecError, Violation

if TYPE_CHECKING:
    from pathlib import Path

    from mli.artifacts import InstallReport

Mode = Literal["global", "local"]
MODES: tuple[Mode, ...] = ("global", "local")

# Placeholder a prompt body may use for the host's own invocation. It is swapped
# for the mode-correct prefix at render time, only for artifacts that opt in.
CLI_TOKEN = "{cli}"


def source_name(source: str) -> str:
    """The name a prompt source contributes, from its path.

    A spec-conformant skill lives in its own directory as ``<name>/SKILL.md``,
    so the *directory* is what names it; every stem in that layout is the
    literal ``SKILL``. Any other file is named by its stem, which is what a
    flat source has always meant.
    """
    if SPEC.is_entry(source):
        return PurePosixPath(source).parent.name
    return PurePosixPath(source).stem


@dataclass(frozen=True)
class Skill:
    """A skill the host ships, installed as a print-on-demand stub.

    ``sources`` are resource paths under the host's prompt package. One source
    makes a plain skill whose frontmatter is lifted verbatim into the stub.
    Several sources make a dispatcher: the stub lists each source's name --
    its directory under the ``<name>/SKILL.md`` layout, its stem otherwise --
    as a subcommand and carries a generated (or ``description``-supplied)
    frontmatter of its own. ``render_cli`` substitutes ``{cli}`` in the bodies
    when they are printed; left unset it follows
    :attr:`Host.render_cli`.
    """

    name: str
    sources: tuple[str, ...]
    description: str | None = None
    render_cli: bool | None = None

    @property
    def kind(self) -> Kind:
        return Kind.SKILL

    @property
    def dispatches(self) -> bool:
        """True when the stub routes between several bodies."""
        return len(self.sources) > 1

    @property
    def subcommands(self) -> tuple[str, ...]:
        """The subcommand names, one per source, in declaration order."""
        return tuple(source_name(source) for source in self.sources)

    @property
    def body_names(self) -> tuple[str, ...]:
        """The names ``<cli> skill <name>`` accepts, one per source.

        A dispatcher's bodies are addressed by their source names, which are
        the subcommands the stub advertises. A single-source skill is addressed
        by the *skill's* name: that is what the model has — it is in the stub's
        frontmatter and in the slash command — and the source file need not be
        named after it.
        """
        return self.subcommands if self.dispatches else (self.name,)

    def source_for(self, subcommand: str) -> str:
        """The source behind ``subcommand``. Raises ``KeyError`` if unknown."""
        for source in self.sources:
            if source_name(source) == subcommand:
                return source
        raise KeyError(subcommand)


@dataclass(frozen=True)
class Rule:
    """A convention rule the host ships, installed as a stamped copy."""

    name: str
    source: str
    render_cli: bool | None = None

    @property
    def kind(self) -> Kind:
        return Kind.RULE


@dataclass(frozen=True)
class Agent:
    """A subagent definition the host ships, installed as a stamped copy."""

    name: str
    source: str
    render_cli: bool | None = None

    @property
    def kind(self) -> Kind:
        return Kind.AGENT


@dataclass(frozen=True)
class Doc:
    """A reference document the host ships, printed and never installed.

    A skill body that defers detail to a sidecar file cannot reach that file
    once the body is printed from a package. Declaring the sidecar as a ``Doc``
    gives it a command — ``<cli> doc <name>`` — that renders it exactly the way
    ``skill`` renders a body, ``{cli}`` included.

    ``name`` may contain ``/`` so a host can namespace its docs by the skill
    that owns them (``tidy/fields``). That is a convention for the host to
    keep, not a rule: nothing here splits on the separator.
    """

    name: str
    source: str
    render_cli: bool | None = None


Artifact = Skill | Rule | Agent

#: Anything that carries a prompt body and an opt-in ``{cli}`` substitution.
Declared = Artifact | Doc


@dataclass(frozen=True)
class ExtraCheck:
    """A host-specific row in the check table, over state ``mli`` cannot see.

    Some of what a host must surface is per-clone, and a correct consumer may
    legitimately lack it — a registered pre-commit hook is the canonical case.
    A hook that never fires looks exactly like a hook that fires and finds
    nothing wrong, so it earns a line; failing the check over it would call a
    correctly installed consumer broken. Hence ``gates``, which lets a row
    report without gating.

    ``status`` is the host's own vocabulary, not :data:`mli.artifacts.Status`.
    Two rules earned the hard way:

    * **Check the artifact, not a proxy for it.** Ask whether *this* host's
      thing is wired, not whether the mechanism that would run it exists — a
      hook runner present in the clone says nothing about whether the config
      names your hook.
    * **Keep "what an attempt did" and "what is" apart.** The status set for a
      write-time follow-up is not the status set for a read-only report;
      collapsing them into one overloaded vocabulary forces a caller to
      overpromise. That applies to anything :attr:`Host.after_install` reports
      too.

    ``gates`` is *this row's verdict*, not a standing policy: only the host
    knows which of its own statuses are failures, so it decides per row. A
    ``True`` row fails the check; a ``False`` row is reported and nothing more.
    ``note`` goes to stderr, for the sentence a one-word status cannot carry.
    """

    label: str
    status: str
    gates: bool
    note: str = ""


@dataclass(frozen=True)
class Host:
    """A package's declaration of its prompts and CLI.

    * ``dist`` is the distribution name, used to look up the installed version
      and to stamp generated files.
    * ``cli`` is the bare command name; in local mode it is prefixed with
      ``local_prefix`` (``uv run`` by default).
    * ``prompts`` is the dotted package that holds the prompt files.
    * ``artifacts`` lists what the host ships.
    * ``docs`` lists the reference documents it ships. They are printed by
      ``<cli> doc <name>`` and never installed, checked, or stamped, so they
      appear here rather than in ``artifacts``.
    * ``render_cli`` is the default for every artifact and doc that leaves its
      own ``render_cli`` unset. A host whose every body uses ``{cli}`` sets it
      once here instead of repeating the flag on each declaration.
    * ``modes`` are the install modes this host supports, in preference order;
      the first is what the CLI uses when given no mode flag. A host whose
      skills only mean anything inside one repository declares
      ``modes=("local",)``, and the other mode stops being reachable at all —
      including by the stray ``install`` that would otherwise write stubs under
      ``$HOME`` and shadow the per-repo ones.
    * ``version`` overrides the metadata lookup; leave it unset in real hosts.
    * ``after_install`` runs once an install has written every artifact, for
      host-specific follow-up such as wiring a pre-commit hook.
    * ``extra_checks`` is its symmetric counterpart on the read side: called
      with ``(host, root, mode)`` during ``install --check``, it returns the
      rows for state ``mli`` cannot derive, so a host with extra state keeps
      the shared table instead of writing its own ``install`` command.
    * ``permissions`` maps each :class:`~mli.permissions.Level` to the Bash
      allow-rules that level *adds* over the one below it; declaring any of
      them mounts the ``permissions`` command. See :mod:`mli.permissions` for
      what the ladder's rungs mean.
    """

    dist: str
    cli: str
    prompts: str
    artifacts: tuple[Artifact, ...] = field(default_factory=tuple)
    docs: tuple[Doc, ...] = field(default_factory=tuple)
    render_cli: bool = False
    modes: tuple[Mode, ...] = MODES
    local_prefix: str = "uv run"
    harness: Harness = CLAUDE_CODE
    version: str | None = None
    after_install: Callable[[InstallReport], None] | None = None
    extra_checks: Callable[[Host, Path, Mode | None], Sequence[ExtraCheck]] | None = (
        None
    )
    permissions: Mapping[Level, tuple[str, ...]] = field(
        default_factory=lambda: MappingProxyType(dict[Level, tuple[str, ...]]())
    )

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        """Reject a declaration the rest of the package cannot serve."""
        if not self.dist or not self.cli or not self.prompts:
            raise ValueError("Host needs a dist, a cli, and a prompts package")
        if not self.modes:
            raise ValueError("Host must support at least one install mode")
        for mode in self.modes:
            if mode not in MODES:
                raise ValueError(
                    f"unknown install mode {mode!r}; choose from: " + ", ".join(MODES)
                )
        if len(set(self.modes)) != len(self.modes):
            raise ValueError("Host declares an install mode twice")
        seen: set[tuple[Kind, str]] = set()
        for art in self.artifacts:
            if not self.harness.supports(art.kind):
                raise ValueError(
                    f"harness {self.harness.name!r} cannot install "
                    f"{art.kind.value} {art.name!r}"
                )
            key = (art.kind, art.name)
            if key in seen:
                raise ValueError(f"duplicate {art.kind.value} {art.name!r}")
            seen.add(key)
            if isinstance(art, Skill):
                if not art.sources:
                    raise ValueError(f"skill {art.name!r} declares no sources")
                subs = art.subcommands
                if len(set(subs)) != len(subs):
                    raise ValueError(
                        f"skill {art.name!r} has sources with duplicate names"
                    )
        # Raises when two bodies would answer to the same `skill <name>`.
        self.skill_sources()
        # Every skill name at once, so an author fixing several sees them all.
        # Only the names: reading and parsing every source here would put a
        # file walk on the import of any package that declares a host, and the
        # file-level rules are what `check_spec` and the harness's own loader
        # are for.
        named = [
            v
            for skill in self.skills
            for v in SPEC.check_declared_name(skill.name, where=f"skill {skill.name!r}")
        ]
        if named:
            raise SpecError(
                named,
                header=f"host {self.dist!r} declares skill names the spec rejects",
            )
        seen_docs: set[str] = set()
        for doc in self.docs:
            if doc.name in seen_docs:
                raise ValueError(f"duplicate doc {doc.name!r}")
            seen_docs.add(doc.name)
            # Docs are the one declared thing nothing else ever touches: they
            # are never installed and never checked, so a typo in `source`
            # would surface only when a model ran the command and got a
            # traceback. An artifact's source is exercised by the first
            # install; a doc's is exercised here or nowhere.
            if not self.has_source(doc.source):
                raise ValueError(
                    f"doc {doc.name!r}: no such prompt {doc.source!r} in {self.prompts}"
                )
        for level in self.permissions:
            if level not in LEVELS:
                raise ValueError(f"unknown permission level {level!r}")
        # `none` is the rung that grants nothing; rules there would make the
        # ladder's floor a lie, since every higher level inherits it.
        if self.permissions.get(Level.none):
            raise ValueError("permission level 'none' must grant nothing")

    # -- identity ----------------------------------------------------------

    def resolved_version(self) -> str:
        """The installed version of the host, or ``0.0.0`` when unknown.

        A missing distribution record (a source checkout that was never
        installed, say) must not make the stub unmanageable, so the fallback
        is a placeholder rather than an error.
        """
        if self.version is not None:
            return self.version
        try:
            return metadata.version(self.dist)
        except metadata.PackageNotFoundError:
            return "0.0.0"

    # -- modes -------------------------------------------------------------

    @property
    def default_mode(self) -> Mode:
        """The mode used when no mode flag is given, and the printing fallback.

        For a two-mode host this is ``global``, which is what a bare ``install``
        has always meant. For a single-mode host it is that mode, so the flag a
        host with one mode has no use for is never required.
        """
        return self.modes[0]

    def supports_mode(self, mode: Mode) -> bool:
        """True when ``mode`` is one this host installs in.

        Spelled out rather than ``supports`` because :class:`~mli.harness.Harness`
        already has one, over artifact kinds; the two answer different questions.
        """
        return mode in self.modes

    def invocation(self, mode: Mode) -> str:
        """The command prefix generated text uses to call this host's CLI."""
        return self.cli if mode == "global" else f"{self.local_prefix} {self.cli}"

    def install_command(self, mode: Mode, *, force: bool = False) -> str:
        """The mode-correct ``install`` command, the one the stamp names."""
        parts = [self.invocation(mode), "install"]
        if mode == "local":
            parts.append("--local")
        if force:
            parts.append("--force")
        return " ".join(parts)

    def check_command(self, mode: Mode) -> str:
        """The mode-correct ``install --check`` command."""
        parts = [self.invocation(mode), "install"]
        if mode == "local":
            parts.append("--local")
        parts.append("--check")
        return " ".join(parts)

    def skill_command(self, mode: Mode, subcommand: str | None = None) -> str:
        """The command that prints a skill body for ``mode``."""
        cmd = f"{self.invocation(mode)} skill"
        return f"{cmd} {subcommand}" if subcommand else cmd

    def doc_command(self, mode: Mode, name: str | None = None) -> str:
        """The command that prints a reference document for ``mode``."""
        cmd = f"{self.invocation(mode)} doc"
        return f"{cmd} {name}" if name else cmd

    # -- prompts -----------------------------------------------------------

    def read(self, source: str) -> str:
        """The text of a bundled prompt, by its path under ``prompts``."""
        return (
            resources.files(self.prompts).joinpath(source).read_text(encoding="utf-8")
        )

    def has_source(self, source: str) -> bool:
        """True when ``source`` names a file inside the ``prompts`` package."""
        return resources.files(self.prompts).joinpath(source).is_file()

    def check_spec(self) -> list[Violation]:
        """Every way this host's skills depart from the Agent Skills spec.

        Reads each source, so it is a deliberate call rather than something
        :meth:`validate` does on import. A host's own test suite is where this
        belongs — see :func:`mli.testing.assert_spec_conformant`.
        """
        return SPEC.check_host(self)

    def renders_cli(self, art: Declared) -> bool:
        """Whether ``art``'s body gets ``{cli}`` substituted.

        The declaration decides when it says so; otherwise the host's own
        :attr:`render_cli` does, so a host whose every body uses the token
        declares it once.
        """
        return self.render_cli if art.render_cli is None else art.render_cli

    # -- artifact lookup ---------------------------------------------------

    def of_kind(self, kind: Kind) -> tuple[Artifact, ...]:
        return tuple(art for art in self.artifacts if art.kind is kind)

    @property
    def skills(self) -> tuple[Skill, ...]:
        return tuple(art for art in self.artifacts if isinstance(art, Skill))

    @property
    def rules(self) -> tuple[Rule, ...]:
        return tuple(art for art in self.artifacts if isinstance(art, Rule))

    @property
    def agents(self) -> tuple[Agent, ...]:
        return tuple(art for art in self.artifacts if isinstance(art, Agent))

    def artifact(self, kind: Kind, name: str) -> Artifact:
        """The declared artifact of ``kind`` named ``name``."""
        for art in self.artifacts:
            if art.kind is kind and art.name == name:
                return art
        raise KeyError(f"{kind.value} {name!r}")

    def doc(self, name: str) -> Doc:
        """The declared doc named ``name``. Raises ``KeyError`` if unknown."""
        for doc in self.docs:
            if doc.name == name:
                return doc
        raise KeyError(f"doc {name!r}")

    def skill_sources(self) -> dict[str, tuple[Skill, str]]:
        """Every skill body by the name ``skill`` prints it under.

        Two namespaces share this mapping: a dispatcher contributes its source
        names, a single-source skill contributes its own name. A name claimed
        twice — by either namespace — is ambiguous and is rejected here rather
        than silently resolved to one of them. :meth:`validate` calls this, so
        a colliding host fails at construction, not at print time.
        """
        out: dict[str, tuple[Skill, str]] = {}
        for skill in self.skills:
            for name, source in zip(skill.body_names, skill.sources, strict=True):
                if name in out:
                    raise ValueError(
                        f"skill body {name!r} is declared by more than one skill"
                    )
                out[name] = (skill, source)
        return out


def names(artifacts: Iterable[Artifact]) -> list[str]:
    """The names of ``artifacts``, in order."""
    return [art.name for art in artifacts]
