"""The shared command grammar, mounted onto a host's own typer app.

A host calls :func:`register` once and gains ``skill``, ``install``, and, when
it declares them, ``rule``, ``agent``, and ``permissions``. Hosts with extra
needs keep writing
their own commands on top of :mod:`mli.artifacts`; the grammar here is the part
that should read the same across every tool.

The ``mli`` console script is the cross-host view: it discovers installed
hosts through the ``mli.hosts`` entry-point group and checks them all.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import typer

from mli import artifacts as install_mod
from mli import permissions as perms
from mli.harness import Kind
from mli.host import Agent, Host, Mode, Rule
from mli.rendering import render_copy, skill_body
from mli.stamp import mli_version

ENTRY_POINT_GROUP = "mli.hosts"


def _err(message: str) -> None:
    typer.echo(message, err=True)


def _print_prompt(text: str) -> None:
    """Print a prompt body, degrading rather than crashing on a narrow stdout.

    Bodies use characters beyond legacy console code pages. A traceback here
    would zero out the stub's only delivery path, so undecodable characters
    are escaped instead.
    """
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if reconfigure is not None:
        reconfigure(errors="backslashreplace")
    typer.echo(text, nl=False)


def _printing_mode(host: Host) -> Mode:
    root = install_mod.find_repo_root(harness=host.harness)
    return install_mod.installed_mode(host, root) or "global"


def _skill_command(host: Host) -> typer.Typer:
    def skill(
        name: str | None = typer.Argument(
            None, help="Skill body to print; omit when the host ships exactly one."
        ),
        list_: bool = typer.Option(False, "--list", help="List the skill bodies."),
    ) -> None:
        """Print a bundled skill's instructions."""
        bodies = host.skill_sources()
        if list_:
            for stem in bodies:
                typer.echo(stem)
            return
        if name is None:
            if len(bodies) != 1:
                _err(
                    f"{host.cli} ships {len(bodies)} skill bodies; name one of: "
                    + ", ".join(bodies)
                )
                raise typer.Exit(1)
            name = next(iter(bodies))
        try:
            skill_, source = bodies[name]
        except KeyError:
            _err(f"unknown skill {name!r}; choose from: " + ", ".join(bodies))
            raise typer.Exit(1) from None
        _print_prompt(skill_body(host, skill_, source, _printing_mode(host)))

    app = typer.Typer()
    app.command("skill")(skill)
    return app


def _copy_command(host: Host, kind: Kind) -> typer.Typer:
    arts = host.of_kind(kind)

    def show(
        name: str | None = typer.Argument(None, help=f"{kind.value} to print."),
        list_: bool = typer.Option(False, "--list", help=f"List the {kind.value}s."),
    ) -> None:
        if list_:
            for art in arts:
                typer.echo(art.name)
            return
        if name is None:
            if len(arts) != 1:
                _err(
                    f"{host.cli} ships {len(arts)} {kind.value}s; name one of: "
                    + ", ".join(a.name for a in arts)
                )
                raise typer.Exit(1)
            name = arts[0].name
        try:
            art = host.artifact(kind, name)
        except KeyError:
            _err(
                f"unknown {kind.value} {name!r}; choose from: "
                + ", ".join(a.name for a in arts)
            )
            raise typer.Exit(1) from None
        if not isinstance(art, Rule | Agent):  # pragma: no cover - kinds are copies
            raise typer.Exit(1)
        _print_prompt(render_copy(host, art, _printing_mode(host), stamp=False))

    show.__doc__ = f"Print a bundled {kind.value} definition."
    app = typer.Typer()
    app.command(kind.value)(show)
    return app


def _relative(path: Path, root: Path) -> Path:
    try:
        return path.relative_to(root)
    except ValueError:
        return path


def run_check(host: Host, root: Path, mode: Mode | None) -> bool:
    """Print the drift table for ``host`` and return whether all rows are ok.

    The host's own :attr:`Host.extra_checks <mli.host.Host.extra_checks>` rows
    print in the same table; only the ones that say they gate fold into the
    verdict.
    """
    typer.echo(
        f"{host.dist} {host.resolved_version()} via mli {mli_version()}, "
        f"harness {host.harness.name}"
    )
    rows = install_mod.check(host, root, mode)
    for row in rows:
        line = f"{row.status:<8}{row.mode:<7}{_relative(row.path, root)}"
        if row.reason:
            line += f"  ({row.reason})"
        typer.echo(line)
    extras = tuple(host.extra_checks(host, root, mode)) if host.extra_checks else ()
    for extra in extras:
        # The mode column is blank: these rows are about the clone, not about a
        # file that exists once per mode.
        typer.echo(f"{extra.status:<8}{'':<7}{extra.label}")
    for extra in extras:
        if extra.note:
            _err(f"note: {extra.note}")
    for path in install_mod.shadowed_skills(host, root):
        _err(
            f"note: a global copy shadows the per-repo stub at "
            f"{_relative(path, root)}; the global one is what loads"
        )
    bad = [row for row in rows if not row.ok]
    # A stale row is not repaired by rewriting the file — the file is the
    # problem. Point at the removal instead of the reinstall that recreates it.
    for row in bad:
        if row.status == "stale":
            _err(f"remove: {_relative(row.path, root)}")
    hinted = {row.mode for row in bad if row.status != "stale"}
    for m in sorted(hinted):
        _err(f"repair: {host.install_command(m, force=True)}")
    return not bad and not any(extra.gates for extra in extras)


def run_install(host: Host, root: Path, mode: Mode, *, force: bool) -> None:
    """Install for ``mode`` and narrate the outcome, exiting 1 on refusal."""
    if mode == "global" and shutil.which(host.cli) is None:
        _err(
            f"warning: `{host.cli}` is not on PATH; a global stub dispatches via "
            f"bare `{host.cli}`. Install it as a tool, or re-run with --local."
        )
    try:
        report = install_mod.install(host, root, mode, force=force)
    except install_mod.ForeignArtifactError as exc:
        _err(
            f"refusing to overwrite {exc.path}: {exc.reason}. "
            "Re-run with --force to replace it."
        )
        raise typer.Exit(1) from None
    except OSError as exc:
        _err(f"cannot write: {exc}")
        raise typer.Exit(1) from None
    for path in report.written:
        typer.echo(f"wrote {_relative(path, root)}")
    for path in report.removed:
        typer.echo(f"removed stale local {_relative(path, root)}")
    for path in report.shadowed:
        _err(
            f"note: a global copy shadows the per-repo stub at "
            f"{_relative(path, root)}; remove it or drop --local"
        )


def _install_command(host: Host) -> typer.Typer:
    def install(
        local: bool = typer.Option(
            False, "--local", help="Install into the enclosing repo instead of ~."
        ),
        check: bool = typer.Option(
            False, "--check", help="Report drift without writing; exit 1 unless ok."
        ),
        force: bool = typer.Option(
            False, "--force", help="Replace files this host did not generate."
        ),
    ) -> None:
        """Materialize the generated files the harness reads, or check them."""
        root = install_mod.find_repo_root(harness=host.harness)
        mode: Mode = "local" if local else "global"
        if check:
            ok = run_check(host, root, mode if local else None)
            raise typer.Exit(0 if ok else 1)
        run_install(host, root, mode, force=force)

    app = typer.Typer()
    app.command("install")(install)
    return app


def _read_settings(path: Path) -> dict[str, object]:
    """Load a settings.json object (empty dict if absent); exit on malformed JSON.

    A missing file is a fresh, empty settings object. A present file must parse
    as a JSON object — a syntax error or a top-level array is a hard error
    rather than a silent overwrite of whatever the user had there. Bytes that
    are not UTF-8 land in the same place: ``UnicodeDecodeError`` is a
    ``ValueError``, not an ``OSError``, so it has to be named to be caught.
    """
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
        _err(f"could not read {path}: {exc}")
        raise typer.Exit(1) from None
    if not isinstance(data, dict):
        _err(f"{path} is not a JSON object; refusing to overwrite it.")
        raise typer.Exit(1)
    return data


def _report_merge(result: perms.MergeResult) -> None:
    for rule in result.added:
        typer.echo(f"  + {rule}")
    for rule in result.already:
        typer.echo(f"  = {rule} (already allowed)")
    for rule, reason in result.skipped:
        _err(f"  ! {rule} skipped ({reason})")


def _permissions_command(host: Host) -> typer.Typer:
    def permissions(
        level: str = typer.Option(
            "assist",
            "--level",
            help="Automation level, lowest to highest: "
            + "|".join(perms.levels())
            + " (or 0-3).",
        ),
        local_: bool = typer.Option(
            True,
            "--local/--global",
            help="Target the repo's .claude/settings.local.json (default) or the "
            "user-wide ~/.claude/settings.json.",
        ),
        apply: bool = typer.Option(
            False,
            "--apply",
            help="Merge the rules into settings.json (default: print them only).",
        ),
    ) -> None:
        """Print or apply an automation-level permission profile.

        Higher levels pre-authorize more of what this tool's skills run, so
        fewer commands prompt. The default prints a paste-ready block; `--apply`
        merges it additively into settings.json, never downgrading an existing
        deny/ask rule.
        """
        try:
            lvl = perms.parse_level(level)
        except ValueError:
            _err(
                f"unknown level: {level!r}; choose from "
                f"{', '.join(perms.levels())} (or 0-3)"
            )
            raise typer.Exit(1) from None

        mode: Mode = "local" if local_ else "global"
        root = install_mod.find_repo_root(harness=host.harness)
        rules = perms.rules_for(host, lvl, mode)
        path = perms.settings_path(root, mode)

        if not apply:
            typer.echo(f"# automation level: {lvl.value} ({mode})")
            typer.echo(f"# target: {_relative(path, root)}")
            if not rules:
                typer.echo("# no rules — everything falls to the classifier")
            typer.echo(perms.render_block(rules), nl=False)
            return

        settings = _read_settings(path)
        existing = settings.get("permissions", {})
        if not isinstance(existing, dict):
            # Same posture as a non-object top level: refuse rather than
            # replace. Merging into `{}` here would drop whatever was there.
            _err(
                f"{path}: 'permissions' is not a JSON object; refusing to overwrite it."
            )
            raise typer.Exit(1)
        result = perms.merge_allow(existing, rules)

        if not result.added:
            # Nothing new to grant: leave the file untouched rather than create
            # or reformat it for a no-op write.
            typer.echo(f"no new rules to add at level {lvl.value} ({mode})")
            _report_merge(result)
            return

        settings["permissions"] = result.permissions
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
        typer.echo(f"wrote {_relative(path, root)} (level {lvl.value}, {mode})")
        _report_merge(result)

    app = typer.Typer()
    app.command("permissions")(permissions)
    return app


def register(app: typer.Typer, host: Host) -> None:
    """Add the shared commands for ``host`` to ``app``."""
    for sub in _commands(host):
        app.registered_commands.extend(sub.registered_commands)


def _commands(host: Host) -> list[typer.Typer]:
    apps = [_skill_command(host), _install_command(host)]
    if host.rules:
        apps.append(_copy_command(host, Kind.RULE))
    if host.agents:
        apps.append(_copy_command(host, Kind.AGENT))
    if host.permissions:
        apps.append(_permissions_command(host))
    return apps


def typer_app(host: Host) -> typer.Typer:
    """A standalone typer app carrying only the shared commands."""
    app = typer.Typer(help=host.dist)
    register(app, host)
    return app


# -- the cross-host `mli` script -------------------------------------------


def discover() -> list[Host]:
    """Every host registered under the ``mli.hosts`` entry-point group."""
    from importlib import metadata

    hosts: list[Host] = []
    for ep in metadata.entry_points(group=ENTRY_POINT_GROUP):
        obj = ep.load()
        if isinstance(obj, Host):
            hosts.append(obj)
    return hosts


mli_app = typer.Typer(help="Cross-host view of installed prompt packages.")


@mli_app.callback(invoke_without_command=True)
def _root(
    ctx: typer.Context,
    version: bool = typer.Option(False, "--version", help="Print the mli version."),
) -> None:
    if version:
        typer.echo(f"mli {mli_version()}")
        raise typer.Exit()
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())


@mli_app.command("hosts")
def _hosts() -> None:
    """List the hosts registered in this environment."""
    found = discover()
    if not found:
        typer.echo("no hosts registered under the mli.hosts entry-point group")
        return
    for host in found:
        kinds = ", ".join(
            f"{len(host.of_kind(kind))} {kind.value}"
            for kind in Kind
            if host.of_kind(kind)
        )
        typer.echo(f"{host.dist} {host.resolved_version()}  ({kinds})")


@mli_app.command("check")
def _check() -> None:
    """Run every registered host's drift check from the current repo."""
    found = discover()
    if not found:
        typer.echo("no hosts registered under the mli.hosts entry-point group")
        raise typer.Exit(1)
    ok = True
    for host in found:
        root = install_mod.find_repo_root(harness=host.harness)
        ok = run_check(host, root, None) and ok
    raise typer.Exit(0 if ok else 1)
