"""mli: the model line interface.

A package that ships prompts as package data declares itself as a
:class:`Host`, and ``mli`` gives it a ``skill`` command that prints those
prompts on demand, an ``install`` command that materializes thin,
version-stamped files where the harness reads them, and a drift check that
tells the two apart.
"""

from mli.artifacts import (
    Check,
    ForeignArtifactError,
    InstallReport,
    artifact_path,
    check,
    find_repo_root,
    install,
)
from mli.cli import register, typer_app
from mli.frontmatter import Frontmatter, split_frontmatter
from mli.harness import CLAUDE_CODE, Harness, Kind
from mli.host import Agent, Artifact, Host, Mode, Rule, Skill
from mli.proc import LOCATION_ENV, run
from mli.rendering import render, render_prompt

__all__ = [
    "CLAUDE_CODE",
    "LOCATION_ENV",
    "Agent",
    "Artifact",
    "Check",
    "ForeignArtifactError",
    "Frontmatter",
    "Harness",
    "Host",
    "InstallReport",
    "Kind",
    "Mode",
    "Rule",
    "Skill",
    "artifact_path",
    "check",
    "find_repo_root",
    "install",
    "register",
    "render",
    "render_prompt",
    "run",
    "split_frontmatter",
    "typer_app",
]
