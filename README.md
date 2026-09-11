# pkgskills

Ship prompts inside a CLI package and install thin, version-stamped stubs
where the harness reads them.

A *host* is a Python package that bundles its Claude Code skills, rules, and
subagent definitions as package data. `pkgskills` gives that package three
things:

- a `skill` command that prints a bundled prompt on demand, so the text an
  agent reads always comes from the installed version and there is no copy to
  go stale;
- an `install` command that materializes the files the harness must read off
  disk, each stamped with the host and `pkgskills` versions, the install mode,
  and the command that regenerates it;
- an `install --check` that tells a current file from a drifted, missing, or
  foreign one and exits non-zero unless everything is `ok`.

Skills are installed as *stubs*: the frontmatter the harness needs to know
when to fire, plus an instruction to run `<cli> skill <name>` and follow the
output.
Rules and agents are installed as *copies*, because the harness reads their
full text with no model in the loop. Both carry the same stamp and the same
drift check. Reference *documents* are the fourth thing a host declares and
the one that is never installed at all: they are printed by `<cli> doc <name>`,
which is how a body defers detail to a sidecar it can no longer reach by path.

## Install

```bash
uv add pkgskills
```

Python 3.11 or later. The only runtime dependency is typer.

## Declare a host

Put the prompts inside the package (hatchling ships `.md` files under a
package directory by default) and declare them once:

```python
# yourtool/cli.py
import typer

from pkgskills import Agent, Doc, Host, Rule, Skill, register

HOST = Host(
    dist="yourtool",  # distribution name, for the version lookup
    cli="yourtool",  # bare command; local mode prefixes `uv run`
    prompts="yourtool.prompts",  # package holding the prompt files
    artifacts=(
        Skill(
            name="yourtool",
            sources=("skills/add/SKILL.md", "skills/close/SKILL.md"),
        ),
        Rule(name="yourtool", source="rules/yourtool.md", render_cli=True),
        Agent(name="yourtool-reviewer", source="agents/reviewer.md"),
    ),
    docs=(Doc(name="add/fields", source="skills/add/references/fields.md"),),
)

app = typer.Typer()
register(app, HOST)  # adds skill, install, doc, rule, agent
```

Each skill source is a spec-conformant skill directory — `<name>/SKILL.md`,
holding the skill's `references/` and `scripts/` too — so the `prompts/` tree
passes a skills linter as it stands. The `skills/` group above is a
convenience, not a requirement: `pkgskills` reads only the last two components
of the path, so a host that ships nothing but skills can drop it and write
`sources=("add/SKILL.md",)`. A flat `skills/add.md` still works and may be
mixed in. `assert_spec_conformant(HOST)` reports anything misfiled, naming the
rule and the fix — see
[docs/source-layout.md](docs/source-layout.md).

A skill with one source lifts that file's frontmatter into the stub, adding
the host and `pkgskills` versions under `metadata` (see
[docs/frontmatter.md](docs/frontmatter.md)). Its body is addressed by the
*skill's* name — `<cli> skill use-solo` — so the source need not be named
after it. A skill with several sources becomes a dispatcher: each source's
name — its directory, or its stem for a flat file — is a subcommand, and the
stub tells the agent to run `<cli> skill <subcommand>`. The two namespaces
share one argument, so a dispatcher subcommand may not collide with another
skill's name; `Host` rejects that at construction, as it rejects a
`Skill.name` outside the spec's grammar.

A body must not point at a file by a path relative to the stub: after
`install` the stub is alone in its directory and there is nothing there to
read. Ship the file as a `Doc` and refer to it as `{cli} doc <name>` — see
[Documents](#documents).

Set `render_cli=True` on an artifact or doc whose body uses the `{cli}`
placeholder; it is rendered as `yourtool` for a global install and
`uv run yourtool` for a local one, so printed commands run as written. When
every body a host ships uses the token, set `render_cli=True` on the `Host`
instead and leave the declarations alone; an explicit flag on a declaration
still wins, so one body can opt back out.

Register the host under the `pkgskills.hosts` entry-point group and the
`pkgskills` script can find it:

```toml
[project.entry-points."pkgskills.hosts"]
yourtool = "yourtool.cli:HOST"
```

## The commands a host gains

| Command | Does |
|---|---|
| `yourtool skill [NAME] [--list]` | Print a skill body, frontmatter stripped. `NAME` is a skill's name, or a dispatcher's subcommand; it is optional when the host ships exactly one body. |
| `yourtool doc [NAME] [--list]` | Print a reference document (only when the host ships docs). |
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
an error naming the host's modes, not a silent redirect, and `pkgskills.install`
refuses it too. The checks that only make sense across two bases — a per-repo
copy gone stale under a global install, a global skill shadowing a local stub
— are skipped, since neither can happen.

This is a per-host constraint. Which mode a *particular repository* expects is
a separate question, and not one `pkgskills` answers yet.

## Documents

A skill body that says "read `references/fields.md` before rewriting anything"
works while the body is a file in a skill directory and stops working the
moment it is printed from a package: there is no directory next to the stub,
and the path resolves to nothing. A `Doc` is that sidecar, declared:

```python
HOST = Host(
    ...,
    docs=(Doc(name="add/fields", source="skills/add/references/fields.md"),),
)
```

The body then says `{cli} doc add/fields`, and the document is printed the same
way a skill body is — frontmatter stripped, `{cli}` resolved for the mode the
install actually resolves to. Because it loads only when a step asks for it,
the detail stays out of context until it is needed.

A doc is not an artifact. It is never written, stamped, checked, or removed;
`install`, `install --check`, and `pkgskills check` do not know it exists, and
the only place it has to ship is the wheel. Names may contain `/` so a host can
namespace its documents by the skill that owns them; that is a convention, not
something `pkgskills` interprets. A doc's name and its source are independent,
which is what lets the file live inside that skill's own directory —
`skills/add/references/fields.md` — so the shipped tree matches the spec's
skill layout while the body still writes `{cli} doc add/fields`. Since nothing else ever reads a doc's `source`, a
missing one is rejected when the `Host` is constructed rather than when a model
runs the command.

A host that would rather keep a print command of its own can: build the body
with `pkgskills.render_prompt(text, host.invocation(mode))` and get `mode` from
`pkgskills.printing_mode(host, root)`, which is what `skill` and `doc` use — the
installed mode when there is one, the host's default before the first install.
Resolving it any other way prints commands that do not run.

## The stamp and the check

Every generated file carries one HTML comment after its frontmatter (or on
the first line when there is none):

```
<!-- generated by yourtool 1.4.0 via pkgskills 0.1.0 (mode=local); do not edit. Regenerate with: uv run yourtool install --local --force -->
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
follow-up such as wiring a pre-commit hook; shell out through
`pkgskills.run(root, argv)`, which pins the call to `root` and strips `GIT_DIR`
and its siblings, so an inherited location variable cannot aim a commit at
another repository.

`Host.extra_checks` is the read side of the same idea. Called with `(host,
root, mode)` during `install --check`, it returns `ExtraCheck(label, status,
gates, note)` rows for per-clone state `pkgskills` cannot see. They print in the
same table, and only the rows that say they gate fold into the exit code — a
hook that is not registered in this clone deserves a line without calling a
correct install broken.

Hosts that need extra flags keep their own `install` command and call
`pkgskills.install(host, root, mode, force=...)` and
`pkgskills.check(host, root, mode)` directly.

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

## The `pkgskills` script

```bash
pkgskills hosts    # every host registered in this environment
pkgskills check    # run each host's drift check from the current repository
```

## Testing a host

`pkgskills.testing.sandbox(tmp_path, monkeypatch)` pins `$HOME` and the working
directory to fresh directories, so a suite never touches the developer's real
`~/.claude`. `pkgskills.testing.wheel_files(project_root, out_dir)` builds a
wheel in-process and lists its contents, which is the only way to prove the
prompts ship: an editable install resolves package data straight to the
checkout.

`pkgskills.testing.assert_spec_conformant(host)` checks every skill the host
ships against the
[Agent Skills specification](https://agentskills.io/specification):
that each source is stored as `<name>/SKILL.md`, that its frontmatter carries a
`name` matching the directory and satisfying the spec's grammar, that a
`description` is present, that `metadata` is the map of strings the spec calls
for (an unquoted `version: 1.0` is a float, not a string), and that no field
runs past its limit. Every
violation is reported at once, each naming the rule it breaks and the fix — see
[docs/source-layout.md](docs/source-layout.md#checking-a-host-against-the-spec).

`pkgskills.testing.assert_prompt_commands(host, app)` closes the loop the whole
pattern exists for. `pkgskills` renders `{cli}`, but nothing otherwise checks
that what follows it is a command the host actually has, and prose about a CLI
goes stale. The helper scans every skill body, doc, rule, and agent for `{cli}
...` mentions, resolves each command path against the typer app, and resolves
the argument to `skill`, `doc`, `rule`, and `agent` against the host's own
declarations — so a renamed doc or a dropped subcommand fails the suite with the
source and line of every mention that no longer reaches anything:

```python
def test_prompts_are_well_formed() -> None:
    assert_spec_conformant(HOST)
    assert_prompt_commands(HOST, app)
```

A mention counts when it is written as code — inside backticks or a fenced
block. Prose that names the bare placeholder ("`{cli}` is substituted per
mode") is talking *about* the token, so the words after it are not read as a
command path. `pkgskills.testing.prompt_commands(host)` returns the same
mentions as `PromptCommand` records (source, line, command path, declared
argument) for a suite that wants to assert something else about them.

## Development

```bash
uv sync --all-groups
uv run pytest
uv run ruff check . && uv run ruff format --check .
uv run pyrefly check
```

`tests/fixtures/` holds three throwaway hosts that the suite drives end to
end: one with every artifact kind, one with a single skill body, and one with
several single-source skills that is also local-only, ships reference
documents inside their own skill directories, and declares `render_cli` once on
the host. All three store their skills the way the spec does, so the tree a
host author copies is conformant as it stands; `brokenhost` is the fourth, and
holds the counterexamples the negative tests need.
