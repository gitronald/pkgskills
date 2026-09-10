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
            sources=("skills/add/SKILL.md", "skills/close/SKILL.md"),
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


# The two commands the bundled bodies tell the model to run. They exist so the
# prompt-command scanner has something real to resolve: a host whose prose
# names commands it does not have is exactly what `assert_prompt_commands`
# catches, and a fixture that never mentions a host-owned command would only
# ever exercise the shared grammar.
@app.command()
def validate(path: str = typer.Argument(".")) -> None:
    """Validate a thing."""
    typer.echo(f"validated {path}")


@app.command()
def close(id_: str = typer.Argument(..., metavar="ID")) -> None:
    """Close a thing."""
    typer.echo(f"closed {id_}")


register(app, HOST)
