"""mli: the model line interface.

A package that ships prompts as package data declares itself as a
:class:`Host`, and ``mli`` gives it a ``skill`` command that prints those
prompts on demand, an ``install`` command that materializes thin,
version-stamped files where the harness reads them, and a drift check that
tells the two apart. A :class:`Doc` is the same print-on-demand delivery for a
reference document a body loads mid-step, with nothing installed at all.
"""

from mli.artifacts import (
    Check,
    ForeignArtifactError,
    InstallReport,
    artifact_path,
    check,
    find_repo_root,
    install,
    installed_mode,
    printing_mode,
)
from mli.cli import register, typer_app
from mli.frontmatter import Block, Frontmatter, find_block, split_frontmatter
from mli.harness import CLAUDE_CODE, Harness, Kind
from mli.host import Agent, Artifact, Doc, ExtraCheck, Host, Mode, Rule, Skill
from mli.permissions import Level
from mli.proc import LOCATION_ENV, run
from mli.rendering import render, render_prompt
from mli.spec import SPEC, Field, SkillSpec, SpecError, Violation

__all__ = [
    "CLAUDE_CODE",
    "LOCATION_ENV",
    "SPEC",
    "Agent",
    "Artifact",
    "Block",
    "Check",
    "Doc",
    "ExtraCheck",
    "Field",
    "ForeignArtifactError",
    "Frontmatter",
    "Harness",
    "Host",
    "InstallReport",
    "Kind",
    "Level",
    "Mode",
    "Rule",
    "Skill",
    "SkillSpec",
    "SpecError",
    "Violation",
    "artifact_path",
    "check",
    "find_block",
    "find_repo_root",
    "install",
    "installed_mode",
    "printing_mode",
    "register",
    "render",
    "render_prompt",
    "run",
    "split_frontmatter",
    "typer_app",
]
