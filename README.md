# mli

Model line interface: ship prompts inside a CLI package and install thin,
version-stamped stubs where the harness reads them.

A *host* is a Python package that bundles its Claude Code skills, rules, and
subagent definitions as package data. `mli` gives that package three things:

- a `skill` command that prints a bundled prompt on demand, so the text an
  agent reads always comes from the installed version and there is no copy to
  go stale;
- an `install` command that materializes the files the harness must read off
  disk, each stamped with the host and `mli` versions, the install mode, and
  the command that regenerates it;
- an `install --check` that tells a current file from a drifted, missing, or
  foreign one and exits non-zero unless everything is `ok`.

Skills are installed as *stubs*: the frontmatter the harness needs to know
when to fire, plus an instruction to run `<cli> skill <name>` and follow the
output.
Rules and agents are installed as *copies*, because the harness reads their
full text with no model in the loop. Both carry the same stamp and the same
drift check.

## Install

```bash
uv add mli
```

Python 3.11 or later. The only runtime dependency is typer.

## Declare a host

Put the prompts inside the package (hatchling ships `.md` files under a
package directory by default) and declare them once:

```python
# yourtool/cli.py
import typer

from mli import Agent, Host, Rule, Skill, register

HOST = Host(
    dist="yourtool",  # distribution name, for the version lookup
    cli="yourtool",  # bare command; local mode prefixes `uv run`
    prompts="yourtool.prompts",  # package holding the prompt files
    artifacts=(
        Skill(name="yourtool", sources=("skills/add.md", "skills/close.md")),
        Rule(name="yourtool", source="rules/yourtool.md", render_cli=True),
        Agent(name="yourtool-reviewer", source="agents/reviewer.md"),
    ),
)

app = typer.Typer()
register(app, HOST)  # adds skill, install, rule, agent
```

A skill with one source lifts that file's frontmatter into the stub, adding
the host and `mli` versions under `metadata` (see
[docs/frontmatter.md](docs/frontmatter.md)). Its body is addressed by the
*skill's* name — `<cli> skill use-solo` — so the source file need not be named
after it. A skill with several sources becomes a dispatcher: each source's
stem is a subcommand, and the stub tells the agent to run
`<cli> skill <subcommand>`. The two namespaces share one argument, so a
dispatcher stem may not collide with another skill's name; `Host` rejects that
at construction.

Set `render_cli=True` on an artifact whose body uses the `{cli}` placeholder;
it is rendered as `yourtool` for a global install and `uv run yourtool` for a
local one, so printed commands run as written.

Register the host under the `mli.hosts` entry-point group and the `mli`
script can find it:

```toml
[project.entry-points."mli.hosts"]
yourtool = "yourtool.cli:HOST"
```

## The commands a host gains

| Command | Does |
|---|---|
| `yourtool skill [NAME] [--list]` | Print a skill body, frontmatter stripped. `NAME` is a skill's name, or a dispatcher's subcommand; it is optional when the host ships exactly one body. |
| `yourtool rule [NAME] [--list]` | Print a rule (only when the host ships rules). |
| `yourtool agent [NAME] [--list]` | Print an agent definition (only when the host ships agents). |
| `yourtool install` | Write every artifact for the host's default mode — under `~/.claude/` unless the host restricts its `modes`. |
| `yourtool install --local` / `--global` | Write them under the enclosing repository, or under `~/.claude/`. Naming a mode the host does not declare is an error. |
| `yourtool install --check` | Report `ok`, `drifted`, `stale`, `missing`, or `foreign` per file; exit 1 unless all ok. |
| `yourtool install --force` | Replace files the host did not generate. |
| `yourtool permissions [--level L] [--global] [--apply]` | Print or apply an automation-level allow-rule profile (only when the host declares one). |

The enclosing repository is the nearest ancestor of the working directory
holding `.git` or `.claude/`, so a local install from a subdirectory still
lands where the harness loads from.

## Modes

**Global** (default) puts one copy under `$HOME` that serves every repository;
the CLI is on `PATH` and invoked bare. **Local** puts the copy under the
repository root and invokes the CLI through `uv run`. The relative layout is
the same at both bases, so the two never collide.

A file's mode is the one its location implies. A stub rendered for local mode
and carried to the global path reads as drifted, because the commands inside
it are wrong where it sits. When both a global and a local copy of a skill
exist, the global one is what the harness loads; `install` and `--check` say
so.

### A host that supports only one

A host whose skills only mean anything inside one repository — they read that
repo's files, or drive its history — has no use for global mode, and a stray
`yourtool install` would write stubs under `$HOME` that then shadow the
per-repo ones. Declare the modes it actually supports:

```python
HOST = Host(..., modes=("local",))
```

The first mode listed is what a flagless `install` uses and what printed
bodies render `{cli}` for before anything is installed, so the flag becomes
optional rather than mandatory. Asking for the other mode (`--global` here) is
an error naming the host's modes, not a silent redirect, and `mli.install`
refuses it too. The checks that only make sense across two bases — a per-repo
copy gone stale under a global install, a global skill shadowing a local stub
— are skipped, since neither can happen.

This is a per-host constraint. Which mode a *particular repository* expects is
a separate question, and not one `mli` answers yet.

## The stamp and the check

Every generated file carries one HTML comment after its frontmatter (or on
the first line when there is none):

```
<!-- generated by yourtool 1.4.0 via mli 0.1.0 (mode=local); do not edit. Regenerate with: uv run yourtool install --local --force -->
```

A skill stub also declares both versions as frontmatter `metadata`, the field
the [Agent Skills specification](https://agentskills.io/specification#frontmatter-required)
reserves for it, so a tool that reads only the frontmatter can tell which
release it has.

`install --check` re-renders each artifact and compares, with every version
token masked, so upgrading either package never flags a file whose content
did not change. What sits at the path decides the verdict:

| At the path | Status | Reason reported |
|---|---|---|
| nothing | `missing` | not installed |
| our render, any versions | `ok` | |
| our stamp, different content | `drifted` | content differs, or rendered for the other mode |
| a local copy a global install superseded | `stale` | still loaded; remove it |
| a file with no stamp | `foreign` | hand-written or from an older release |
| another package's stamp | `foreign` | generated by that package |
| a symlink, dangling or live | `foreign` | a symlink, not a plain file |
| a directory | `foreign` | a directory, not a file |
| unreadable or not UTF-8 | `foreign` | unreadable |

`install` refuses to touch a foreign file without `--force`, and it checks
every target before writing the first one, so a refused rule never leaves a
half-installed skill behind. With `--force`, a symlink is replaced by a plain
file rather than written through. A fresh global install removes per-repo
copies the host generated earlier; a local install never deletes the global
copy that serves other repositories.

`stale` is the asymmetric case. The harness auto-loads rules and agents from
the global *and* the local location at once, so a per-repo copy left behind
after a switch to global is an extra file live in context whatever its content
says. The verdict therefore outranks both `ok` and `drifted`: the check gates on
it and says `remove:`, not `repair:` — rewriting the file is not the fix, and a
reinstall would only recreate it. Skills are exempt, because a
global skill shadows the local stub rather than loading alongside it; which
kinds load from both bases is declared on the `Harness`. A *global* copy during
a local install is never flagged: it is shared infrastructure serving every
other repository.

## Hooks for host-specific work

`Host.after_install` receives an `InstallReport` (mode, root, and the paths
written, removed, and shadowed) once every artifact is on disk. Use it for
follow-up such as wiring a pre-commit hook; shell out through `mli.run(root,
argv)`, which pins the call to `root` and strips `GIT_DIR` and its siblings, so
an inherited location variable cannot aim a commit at another repository.

`Host.extra_checks` is the read side of the same idea. Called with `(host,
root, mode)` during `install --check`, it returns `ExtraCheck(label, status,
gates, note)` rows for per-clone state `mli` cannot see. They print in the same
table, and only the rows that say they gate fold into the exit code — a hook
that is not registered in this clone deserves a line without calling a correct
install broken.

Hosts that need extra flags keep their own `install` command and call
`mli.install(host, root, mode, force=...)` and `mli.check(host, root, mode)`
directly.

## Automation levels

A host whose skills tell the model to run commands can declare, per level, the
Bash allow-rules that level adds:

```python
HOST = Host(
    ...,
    permissions={
        Level.assist: ("Bash(git add:*)", "Bash(git commit:*)", "Bash(uv run:*)"),
        Level.confirm: ("Bash(git push:*)",),
        Level.full: ("Bash(gh pr merge:*)",),
    },
)
```

The levels are an escalating, superset ladder named by supervision posture —
`none` (grant nothing), `assist` (local and reversible), `confirm` (adds the
publishing step), `full` (adds the irreversible one) — with `0`–`3` as
aliases. `yourtool permissions` prints the cumulative union for a level; the
grant for calling the CLI itself is derived from the host's invocation, so it
appears for a global profile and collapses into `Bash(uv run:*)` for a local
one.

`--apply` merges into `.claude/settings.local.json` (or `~/.claude/settings.json`
with `--global`). The merge is additive and never downgrades: a rule already on
`deny` or `ask` stays there and is reported as skipped, a rule already allowed
is a no-op, and an apply with nothing to add leaves the file untouched. So the
command is safe to run blind.

## The `mli` script

```bash
mli hosts    # every host registered in this environment
mli check    # run each host's drift check from the current repository
```

## Testing a host

`mli.testing.sandbox(tmp_path, monkeypatch)` pins `$HOME` and the working
directory to fresh directories, so a suite never touches the developer's real
`~/.claude`. `mli.testing.wheel_files(project_root, out_dir)` builds a wheel
in-process and lists its contents, which is the only way to prove the prompts
ship: an editable install resolves package data straight to the checkout.

## Development

```bash
uv sync --all-groups
uv run pytest
uv run ruff check . && uv run ruff format --check .
uv run pyrefly check
```

`tests/fixtures/` holds three throwaway hosts that the suite drives end to
end: one with every artifact kind, one with a single skill body, and one with
several single-source skills (whose bodies do not all match their file stems).
