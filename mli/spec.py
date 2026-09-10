"""The Agent Skills specification, encoded as data and as a check.

``docs/agentskills-specification.md`` is the prose; this module is the part of
it ``mli`` can enforce. Everything the spec fixes — the entry filename, the
directories a skill may hold, the frontmatter fields and their limits, the
``name`` grammar and its tie to the parent directory — lives on
:class:`SkillSpec`, and :data:`SPEC` is the singleton the rest of the package
uses.

The point of holding it as data rather than as scattered ``if`` statements is
the error message. A host author who mis-stores a skill gets told which rule
was broken, what the file actually says, and what to do about it — with the
spec's own layout printed alongside — instead of a traceback from whichever
renderer happened to touch it first. :meth:`SkillSpec.check_host` collects
*every* violation rather than stopping at the first, because a source that is
wrong in one way is usually wrong in two.

``metadata`` is checked too, though :func:`mli.frontmatter.parse_fields`
flattens it to an empty string: the spec calls it *a map from string keys to
string values*, and :func:`mli.frontmatter.find_block` hands back the raw
mapping so the map-ness can be inspected. The rule that earns its keep is the
value one — the spec's own example writes ``version: "1.0"`` with the quotes
because unquoted it is a float, and ``mli`` quotes the two keys it writes there
(:mod:`mli.stamp`) for exactly that reason.

What is *not* checked is the spec's recommendations, as against its
constraints: that a description name what the skill does *and* when to use it,
that ``SKILL.md`` stay under 500 lines, that references sit one level deep.
Those are advice to an author, and a check that fails a host over them would be
asserting a house style the specification does not.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import TYPE_CHECKING

from mli.frontmatter import Block, Frontmatter, find_block, split_frontmatter

if TYPE_CHECKING:
    from mli.host import Host, Skill

#: The reference validator the spec points at, named in the repair advice.
VALIDATOR = "skills-ref validate"

#: Unquoted scalars YAML resolves to something other than a string. The spec
#: requires string values under ``metadata``, and a bare ``1.0`` is a float.
_NOT_STRINGS: tuple[tuple[str, str], ...] = (
    (r"[-+]?\d+", "an integer"),
    (r"[-+]?(\d+\.\d*|\.?\d+)([eE][-+]?\d+)?", "a float"),
    (r"true|false|yes|no|on|off", "a boolean"),
    (r"null|~", "a null"),
)


def _not_a_string(value: str) -> str | None:
    """What YAML would read ``value`` as, when that is not a string."""
    if len(value) >= 2 and value[0] in "\"'" and value[-1] == value[0]:
        return None  # quoted, so a string whatever it looks like
    for pattern, reads_as in _NOT_STRINGS:
        if re.fullmatch(pattern, value, re.IGNORECASE):
            return reads_as
    return None


@dataclass(frozen=True)
class Field:
    """One frontmatter field, with the spec's own constraint on it."""

    name: str
    required: bool
    constraint: str
    #: Maximum length in characters, when the spec sets one.
    max_length: int | None = None


@dataclass(frozen=True)
class Violation:
    """One way a skill departs from the spec.

    ``where`` is the source path the problem is in, or the declaration that
    carries it when no single file is at fault. ``rule`` is a stable slug so a
    caller can filter; ``detail`` says what is actually wrong and ``fix`` what
    to do about it.
    """

    where: str
    rule: str
    detail: str
    fix: str

    def __str__(self) -> str:
        return f"{self.where}: {detail_line(self)}"


def detail_line(v: Violation) -> str:
    return f"{v.detail} [{v.rule}] -- {v.fix}"


@dataclass(frozen=True)
class SkillSpec:
    """The Agent Skills specification's rules for one skill.

    Defaults are the spec as written; they are fields rather than constants so
    a caller can pin an older or stricter reading without forking the checks.
    """

    #: The required entry file. Matched exactly — the spec writes it uppercase.
    entry_file: str = "SKILL.md"
    #: Directories the spec names as conventional inside a skill.
    optional_dirs: tuple[str, ...] = ("scripts", "references", "assets")
    #: The `name` grammar: lowercase alphanumerics in hyphen-separated runs.
    name_pattern: str = r"[a-z0-9]+(?:-[a-z0-9]+)*"
    fields: tuple[Field, ...] = (
        Field(
            "name",
            required=True,
            constraint=(
                "1-64 characters of a-z, 0-9 and hyphens, no leading, trailing "
                "or consecutive hyphen, and equal to the parent directory name"
            ),
            max_length=64,
        ),
        Field(
            "description",
            required=True,
            constraint=(
                "1-1024 characters saying what the skill does and when to use it"
            ),
            max_length=1024,
        ),
        Field(
            "license",
            required=False,
            constraint="a license name, or the name of a bundled license file",
        ),
        Field(
            "compatibility",
            required=False,
            constraint="up to 500 characters of environment requirements",
            max_length=500,
        ),
        Field(
            "metadata",
            required=False,
            constraint="a mapping of string keys to string values",
        ),
        Field(
            "allowed-tools",
            required=False,
            constraint="a space-separated string of pre-approved tools",
        ),
    )

    # -- the layout --------------------------------------------------------

    def structure(self, name: str = "skill-name") -> str:
        """The spec's directory diagram, for an error message to quote."""
        entries = [(self.entry_file, "required")]
        entries += [(f"{d}/", "optional") for d in self.optional_dirs]
        width = max(len(entry) for entry, _ in entries) + 2
        lines = [f"{name}/"]
        for i, (entry, note) in enumerate(entries):
            elbow = "└──" if i == len(entries) - 1 else "├──"
            lines.append(f"{elbow} {entry.ljust(width)}# {note}")
        return "\n".join(lines)

    def is_entry(self, source: str) -> bool:
        """True when ``source`` is stored as the spec's ``<name>/SKILL.md``."""
        path = PurePosixPath(source)
        return path.name == self.entry_file and bool(path.parent.name)

    def directory(self, source: str) -> str:
        """The skill directory ``source`` sits in, or ``""`` if it is flat."""
        path = PurePosixPath(source)
        return str(path.parent) if self.is_entry(source) else ""

    # -- the name ----------------------------------------------------------

    def name_problem(self, name: str) -> str | None:
        """Why ``name`` breaks the spec's grammar, or ``None`` when it does not.

        The reasons are separated because "invalid" alone leaves the author
        guessing which of five rules they tripped.
        """
        limit = self.field("name").max_length
        if not name:
            return "it is empty"
        if limit is not None and len(name) > limit:
            return f"it is {len(name)} characters, over the {limit}-character limit"
        if name.startswith("-") or name.endswith("-"):
            return "it starts or ends with a hyphen"
        if "--" in name:
            return "it contains consecutive hyphens"
        if name.lower() != name:
            return "it contains uppercase characters"
        if re.fullmatch(self.name_pattern, name) is None:
            return "it contains characters outside a-z, 0-9 and hyphens"
        return None

    def valid_name(self, name: str) -> bool:
        return self.name_problem(name) is None

    # -- metadata ----------------------------------------------------------

    def check_metadata(self, source: str, front: Frontmatter) -> list[Violation]:
        """Violations in the ``metadata`` mapping, if the source declares one.

        The spec makes it *a map from string keys to string values*, so three
        things are wrong here: a scalar or a sequence where a map belongs, a
        value that is itself a mapping, and a value YAML will not hand back as
        a string. The last is the one that bites in practice — the spec's own
        example writes ``version: "1.0"`` with the quotes precisely because
        unquoted it is a float.
        """
        if "metadata" not in front.fields:
            return []
        block = find_block(front.raw, "metadata")
        if block is None:  # pragma: no cover - fields and raw cannot disagree
            return []
        return self.check_metadata_block(source, block)

    def check_metadata_block(self, source: str, block: Block) -> list[Violation]:
        """Violations in the ``metadata`` block itself, already located.

        Split from :meth:`check_metadata` so a caller holding the block —
        :func:`mli.rendering.with_metadata` splices into it — can ask what is
        wrong with it without re-finding it.
        """

        def wrong(rule: str, detail: str, fix: str) -> Violation:
            return Violation(where=source, rule=rule, detail=detail, fix=fix)

        if block.inline:
            return [
                wrong(
                    "metadata-not-a-mapping",
                    f"`metadata` is the scalar {block.inline!r}",
                    "make it a mapping of string keys to string values, "
                    "indented on the lines below `metadata:`",
                )
            ]
        entries = block.entries()
        if not entries:
            return [
                wrong(
                    "metadata-not-a-mapping",
                    "`metadata` opens no mapping, so it reads back as null",
                    "give it at least one `key: value` pair, or drop the key",
                )
            ]
        out: list[Violation] = []
        base = entries[0][0]
        top = [(key, value) for indent, key, value in entries if indent <= base]
        # A sequence is one wrong shape, not one per item: `- a` and `- b` say
        # the same thing about the block, so reporting each would bury the
        # entries that are genuinely worth a line of their own.
        if loose := [value for key, value in top if not key]:
            out.append(
                wrong(
                    "metadata-not-a-mapping",
                    "`metadata` holds "
                    + ", ".join(repr(v) for v in loose[:3])
                    + (", ..." if len(loose) > 3 else "")
                    + ", which declares no key",
                    "every entry must be a `key: value` pair",
                )
            )
        for key, value in top:
            if not key:
                continue
            if not value:
                out.append(
                    wrong(
                        "metadata-value-not-a-string",
                        f"`metadata.{key}` has no scalar value",
                        "give it a string; the spec allows no nested mappings, "
                        "sequences, or nulls under `metadata`",
                    )
                )
            elif problem := _not_a_string(value):
                out.append(
                    wrong(
                        "metadata-value-not-a-string",
                        f"`metadata.{key}` is {value!r}, which YAML reads as "
                        f"{problem}, not a string",
                        f'quote it -- `{key}: "{value}"`',
                    )
                )
        return out

    # -- lookups -----------------------------------------------------------

    def field(self, name: str) -> Field:
        for spec_field in self.fields:
            if spec_field.name == name:
                return spec_field
        raise KeyError(name)

    @property
    def required_fields(self) -> tuple[Field, ...]:
        return tuple(f for f in self.fields if f.required)

    # -- the checks --------------------------------------------------------

    def check_declared_name(self, name: str, *, where: str) -> list[Violation]:
        """Violations in a name a host declared, before any file is read."""
        problem = self.name_problem(name)
        if problem is None:
            return []
        return [
            Violation(
                where=where,
                rule="name-grammar",
                detail=f"skill name {name!r} is invalid: {problem}",
                fix=f"rename it to satisfy {self.field('name').constraint}",
            )
        ]

    def check_layout(self, source: str) -> list[Violation]:
        """Violations in where a source is stored.

        A flat source is a departure from the spec but not an error ``mli``
        raises on: hosts predating the layout keep working, and the rule slug
        lets a caller decide how loudly to say so.
        """
        if self.is_entry(source):
            return []
        return [
            Violation(
                where=source,
                rule="entry-file",
                detail=(
                    f"the source is a flat file, not a {self.entry_file} inside a "
                    "directory named for the skill"
                ),
                fix=(
                    f"move it to <name>/{self.entry_file}, so a skill is a "
                    # Indented past the bullet `report` puts this line behind,
                    # so the diagram reads as part of it rather than as a
                    # sibling of the next file's heading.
                    f"directory:\n{indent(self.structure(), ' ' * 6)}"
                ),
            )
        ]

    def check_frontmatter(self, source: str, text: str) -> list[Violation]:
        """Violations in a source's frontmatter block, read from its text."""
        front, _ = split_frontmatter(text)
        return self.check_parsed(source, front)

    def check_parsed(self, source: str, front: Frontmatter | None) -> list[Violation]:
        """Violations in an already-split frontmatter block.

        The parsed form is the parameter because a caller that needs the block
        *and* its violations — :func:`mli.rendering.stub_frontmatter` renders
        the one and reports the other — would otherwise split the same text
        twice.
        """
        if front is None:
            return [
                Violation(
                    where=source,
                    rule="frontmatter-missing",
                    detail="the file opens with no `---` frontmatter block",
                    fix=(
                        "start it with a block declaring "
                        + " and ".join(f.name for f in self.required_fields)
                    ),
                )
            ]
        out: list[Violation] = []
        for spec_field in self.fields:
            value = front.get(spec_field.name)
            if value is None or not value.strip():
                if spec_field.required:
                    out.append(
                        Violation(
                            where=source,
                            rule=f"{spec_field.name}-missing",
                            detail=f"frontmatter declares no `{spec_field.name}`",
                            fix=f"add `{spec_field.name}`: {spec_field.constraint}",
                        )
                    )
                continue
            limit = spec_field.max_length
            if limit is not None and len(value) > limit:
                out.append(
                    Violation(
                        where=source,
                        rule=f"{spec_field.name}-too-long",
                        detail=(
                            f"`{spec_field.name}` is {len(value)} characters, over "
                            f"the {limit}-character limit"
                        ),
                        fix=f"shorten it: {spec_field.constraint}",
                    )
                )
        out.extend(self.check_metadata(source, front))
        declared = front.get("name")
        if declared:
            name_problem = self.name_problem(declared)
            out.extend(self.check_declared_name(declared, where=source))
            directory = self.directory(source)
            parent = PurePosixPath(directory).name if directory else ""
            if parent and parent != declared:
                out.append(
                    Violation(
                        where=source,
                        rule="name-matches-directory",
                        detail=(
                            f"frontmatter names {declared!r} but the directory is "
                            f"{parent!r}; the spec requires they match"
                        ),
                        # Never advise renaming a directory to a name the
                        # grammar rejects — that trades one violation for two.
                        fix=(
                            f"set the `name` to {parent!r}"
                            if name_problem is not None
                            else f"rename the directory to {declared!r}, or set the "
                            f"`name` to {parent!r}"
                        ),
                    )
                )
        return out

    # -- whole declarations ------------------------------------------------

    def check_skill(self, host: Host, skill: Skill) -> list[Violation]:
        """Every violation in one declared skill, sources read."""
        where = f"skill {skill.name!r}"
        out = self.check_declared_name(skill.name, where=where)
        for source in skill.sources:
            out.extend(self.check_layout(source))
            if not host.has_source(source):
                out.append(
                    Violation(
                        where=source,
                        rule="source-missing",
                        detail=f"no such prompt in the {host.prompts} package",
                        fix="ship the file as package data, or fix the path",
                    )
                )
                continue
            out.extend(self.check_frontmatter(source, host.read(source)))
        return out

    def check_host(self, host: Host) -> list[Violation]:
        """Every violation across every skill ``host`` declares."""
        return [v for skill in host.skills for v in self.check_skill(host, skill)]


#: The spec as written, and what every caller in ``mli`` uses.
SPEC = SkillSpec()


def indent(text: str, prefix: str = "    ") -> str:
    return "\n".join(prefix + line for line in text.splitlines())


def group(violations: Iterable[Violation]) -> Iterator[tuple[str, list[Violation]]]:
    """``violations`` bucketed by ``where``, in first-seen order."""
    buckets: dict[str, list[Violation]] = {}
    for v in violations:
        buckets.setdefault(v.where, []).append(v)
    yield from buckets.items()


def report(violations: Iterable[Violation], *, header: str) -> str:
    """A multi-violation message, grouped by the file each is in."""
    blocks = [
        "\n".join([f"  {where}:", *(f"    - {detail_line(v)}" for v in found)])
        for where, found in group(violations)
    ]
    return "\n".join([header, *blocks])


class SpecError(ValueError):
    """Raised when a host's skills depart from the spec in a way that blocks.

    Carries the violations as data so a caller that wants to present them
    differently does not have to parse the message back apart. Deliberately a
    ``ValueError``: every declaration problem ``Host`` already rejects is one,
    and a host author's ``except ValueError`` should not start missing cases
    because the message got better.
    """

    def __init__(
        self,
        violations: Iterable[Violation],
        *,
        header: str = "skill sources do not follow the Agent Skills specification",
    ) -> None:
        self.violations: tuple[Violation, ...] = tuple(violations)
        self.header = header
        super().__init__(report(self.violations, header=header))
