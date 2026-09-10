"""A throwaway host with a single skill body, used by the test suite."""

from __future__ import annotations

from mli import Host, Skill, typer_app

HOST = Host(
    dist="solohost",
    cli="solohost",
    prompts="solohost.prompts",
    version="0.9.0",
    artifacts=(Skill(name="use-solo", sources=("use-solo/SKILL.md",)),),
)

app = typer_app(HOST)
