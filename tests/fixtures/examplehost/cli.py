"""A throwaway host with every artifact kind, used by the test suite."""

from __future__ import annotations

import typer

from mli import Agent, Host, Rule, Skill, register

HOST = Host(
    dist="examplehost",
    cli="examplehost",
    prompts="examplehost.prompts",
    version="1.2.3",
    artifacts=(
        Skill(
            name="example",
            sources=("skills/add.md", "skills/close.md"),
            render_cli=True,
        ),
        Rule(name="examplehost", source="rules/examplehost.md", render_cli=True),
        Agent(name="example-reviewer", source="agents/example-reviewer.md"),
    ),
)

app = typer.Typer(help="examplehost")


@app.command()
def hello() -> None:
    """A command of the host's own, alongside the shared ones."""
    typer.echo("hello from examplehost")


register(app, HOST)
