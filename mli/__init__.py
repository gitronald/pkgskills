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
from mli.frontmatter import Frontmatter, split_frontmatter
from mli.harness import CLAUDE_CODE, Harness, Kind
from mli.host import Agent, Artifact, Doc, ExtraCheck, Host, Mode, Rule, Skill
from mli.permissions import Level
from mli.proc import LOCATION_ENV, run
from mli.rendering import render, render_prompt

__all__ = [
    "CLAUDE_CODE",
    "LOCATION_ENV",
    "Agent",
    "Artifact",
    "Check",
    "Doc",
    "ExtraCheck",
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
    "artifact_path",
    "check",
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
