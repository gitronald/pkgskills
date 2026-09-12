"""pkgskills: skills that ship inside a CLI's own package.

A package that ships prompts as package data declares itself as a
:class:`Host`, and ``pkgskills`` gives it a ``skill`` command that prints those
prompts on demand, an ``install`` command that materializes thin,
version-stamped files where the harness reads them, and a drift check that
tells the two apart. A :class:`Doc` is the same print-on-demand delivery for a
reference document a body loads mid-step, with nothing installed at all.
"""

from pkgskills.artifacts import (
    Check,
    ForeignArtifactError,
    InstallReport,
    LineCheck,
    LineWrite,
    artifact_path,
    check,
    check_lines,
    find_repo_root,
    install,
    installed_mode,
    printing_mode,
)
from pkgskills.cli import register, typer_app
from pkgskills.frontmatter import Frontmatter, split_frontmatter
from pkgskills.harness import CLAUDE_CODE, Harness, Kind
from pkgskills.host import (
    Agent,
    Artifact,
    Doc,
    ExtraCheck,
    Host,
    Line,
    Mode,
    Rule,
    Skill,
)
from pkgskills.permissions import Level
from pkgskills.precommit import Hook, HookReport
from pkgskills.proc import LOCATION_ENV, run
from pkgskills.rendering import render, render_prompt
from pkgskills.spec import SPEC, Field, SkillSpec, SpecError, Violation

__all__ = [
    "CLAUDE_CODE",
    "LOCATION_ENV",
    "SPEC",
    "Agent",
    "Artifact",
    "Check",
    "Doc",
    "ExtraCheck",
    "Field",
    "ForeignArtifactError",
    "Frontmatter",
    "Harness",
    "Hook",
    "HookReport",
    "Host",
    "InstallReport",
    "Kind",
    "Level",
    "Line",
    "LineCheck",
    "LineWrite",
    "Mode",
    "Rule",
    "Skill",
    "SkillSpec",
    "SpecError",
    "Violation",
    "artifact_path",
    "check",
    "check_lines",
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
