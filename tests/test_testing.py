"""Tests for the helpers host suites import."""

from __future__ import annotations

import dataclasses
import os
from pathlib import Path

import pytest
from examplehost.cli import HOST as EXAMPLE
from examplehost.cli import app as example_app
from multihost.cli import HOST as MULTI
from multihost.cli import app as multi_app
from solohost.cli import HOST as SOLO
from solohost.cli import app as solo_app

from mli import Doc, Host, typer_app
from mli.testing import (
    PromptCommand,
    Sandbox,
    assert_prompt_commands,
    prompt_commands,
    wheel_files,
)

PROJECT = Path(__file__).parents[1]


def test_sandbox_pins_home_and_cwd(box: Sandbox) -> None:
    assert Path.home() == box.home
    assert Path.cwd() == box.repo
    assert (box.repo / ".git").is_dir()
    assert os.environ["HOME"] == str(box.home)


def test_wheel_ships_the_package(tmp_path: Path) -> None:
    files = wheel_files(PROJECT, tmp_path / "dist")
    assert "mli/rendering.py" in files
    assert "mli/py.typed" in files
    assert not any(name.startswith("tests/") for name in files)


# -- prompt commands --------------------------------------------------------


def found(host: Host, source: str) -> list[PromptCommand]:
    """The mentions from one source, for a compact assertion."""
    return [cmd for cmd in prompt_commands(host) if cmd.source == source]


def test_scans_every_declared_prompt() -> None:
    sources = {cmd.source for cmd in prompt_commands(EXAMPLE)}
    # The rule is scanned alongside the two skill bodies; the agent declares no
    # `{cli}` at all, which is why it contributes nothing rather than failing.
    assert sources == {
        "skills/add/SKILL.md",
        "skills/close/SKILL.md",
        "rules/examplehost.md",
    }


def test_reads_a_fenced_command() -> None:
    (cmd,) = found(EXAMPLE, "skills/add/SKILL.md")
    assert cmd.tokens == ("validate",)
    assert cmd.argument is None
    assert cmd.text == "{cli} validate"


def test_stops_at_a_placeholder_argument() -> None:
    (cmd,) = found(EXAMPLE, "skills/close/SKILL.md")
    assert cmd.tokens == ("close",)
    assert cmd.argument is None


def test_reads_a_declared_argument() -> None:
    by_line = {cmd.line: cmd for cmd in found(MULTI, "skills/tidy/SKILL.md")}
    doc_cmd = next(c for c in by_line.values() if c.tokens == ("doc",))
    assert doc_cmd.argument == "tidy/fields"
    assert doc_cmd.text == "{cli} doc tidy/fields"


def test_reads_an_option_as_the_end_of_the_path() -> None:
    cmds = found(MULTI, "skills/audit-body.md")
    assert ("install",) in {cmd.tokens for cmd in cmds}


def test_resolves_an_argument_of_each_declaring_command() -> None:
    named = {
        cmd.tokens[0]: cmd.argument
        for cmd in found(EXAMPLE, "rules/examplehost.md")
        if cmd.argument is not None
    }
    assert named == {
        "skill": "add",
        "rule": "examplehost",
        "agent": "example-reviewer",
    }


def test_an_option_is_not_a_declared_argument() -> None:
    listing = [
        cmd
        for cmd in found(EXAMPLE, "rules/examplehost.md")
        if cmd.tokens == ("skill",) and cmd.argument is None
    ]
    assert len(listing) == 1


def test_prose_mention_is_not_a_command() -> None:
    # solohost's body names the bare token in a sentence, outside any code
    # span, precisely so nothing reads the following words as a command path.
    assert prompt_commands(SOLO) == []


def test_prose_mention_in_a_doc_is_not_a_command() -> None:
    lines = {cmd.line for cmd in found(MULTI, "references/tidy/fields.md")}
    assert lines == {5}


def test_a_real_argument_to_a_leaf_command_is_not_a_subcommand() -> None:
    # `{cli} close fix-typo` is tokens the same shape as a command path, so the
    # scanner records both; only the app knows `close` takes an argument.
    # Resolution stops at the leaf, which is what lets a body write a realistic
    # example instead of a placeholder.
    (cmd,) = [
        c for c in found(EXAMPLE, "rules/examplehost.md") if c.tokens[0] == "close"
    ]
    assert cmd.tokens == ("close", "fix-typo")
    assert_prompt_commands(EXAMPLE, example_app)


def test_every_command_the_fixtures_name_is_real() -> None:
    assert_prompt_commands(EXAMPLE, example_app)
    assert_prompt_commands(MULTI, multi_app)
    assert_prompt_commands(SOLO, solo_app)


def test_reports_an_unknown_command_and_an_undeclared_doc() -> None:
    # Only the stale doc, so the two failures are the whole message. Its app is
    # built from the same declaration, which is what mounts `doc` at all — the
    # undeclared *name* is the failure, not a missing command.
    host = dataclasses.replace(
        EXAMPLE,
        artifacts=(),
        docs=(Doc(name="broken", source="references/broken.md"),),
    )
    with pytest.raises(AssertionError) as exc:
        assert_prompt_commands(host, typer_app(host))
    message = str(exc.value)
    assert "references/broken.md:6: {cli} nonexistent -- no such command" in message
    assert "{cli} doc no-such-doc -- no doc 'no-such-doc' is declared" in message
    # The same words in prose on line 8 are not reported.
    assert "references/broken.md:8" not in message
