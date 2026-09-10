# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- `Host` declaration: distribution name, CLI name, prompt package, and the
  skills, rules, agents, and reference documents a package ships, with an
  `after_install` hook.
- `register(app, host)` mounts the shared grammar on a host's typer app:
  `skill`, `install`, and, when declared, `doc`, `rule` and `agent`.
- `Doc` declares a reference document a skill body loads mid-step. It is
  printed by `<cli> doc <name>` — the same render a skill body gets — and is
  never installed, stamped, or checked, so it sits on `Host.docs` rather than
  in `Host.artifacts`. Names may contain `/` for namespacing, and a source
  that does not exist is rejected at construction.
- `printing_mode(host, root)` and `installed_mode(host, root)` are exported,
  so a host with a print command of its own resolves `{cli}` the way `skill`
  and `doc` do.
- `Host.render_cli` is the default for every artifact and doc that leaves its
  own `render_cli` unset, for a host whose every body uses the placeholder. An
  explicit flag on a declaration still wins.
- Skills install as print-on-demand stubs, each naming the body it prints
  (`<cli> skill <name>`); a multi-source skill becomes a dispatcher whose
  subcommands are the source stems, while a single-source skill is addressed
  by the skill's own name, whatever its source file is called. Rules and
  agents install as stamped copies.
- Global (`~/.claude/`) and local (repository) install modes, with the
  repository root found by walking up to `.git` or `.claude/`.
- `Host.modes` declares which install modes a host supports, in preference
  order; the first is used by a flagless `install` and by `{cli}` rendering
  before anything is installed. A host bound to one repository declares
  `modes=("local",)`: `--global` is then refused by name, `mli.install` refuses
  it too, and the stale-local and shadowed-stub checks are skipped. `install`
  takes `--local/--global` rather than only `--local`.
- Skill stubs declare the host and `mli` versions as frontmatter `metadata`
  (`version`, `mli-version`), the field the [Agent Skills
  specification](https://agentskills.io/specification#frontmatter-required)
  reserves for client properties; `docs/frontmatter.md` covers the shape.
- One stamp format naming the host version, the `mli` version, the mode, and
  the regenerate command; `install --check` masks every version and reports
  `ok`, `drifted`, `missing`, or `foreign` with a reason per file.
- Foreign files (unstamped, another package's stamp, symlinks, directories,
  undecodable bytes) are never replaced without `--force`, and every target
  is guarded before the first write.
- `{cli}` placeholder rendering per mode for artifacts and docs that opt in.
- `mli hosts` and `mli check` over the `mli.hosts` entry-point group.
- `mli.testing.sandbox` and `mli.testing.wheel_files` for host test suites.
- `mli.testing.prompt_commands(host)` and
  `mli.testing.assert_prompt_commands(host, app)` check that every `{cli} ...`
  mention in a host's skills, docs, rules, and agents names a command the typer
  app really has, and that the argument to `skill`, `doc`, `rule`, or `agent`
  names something the host declares. Mentions count only where they are written
  as code, so prose about the placeholder is not read as a command.
- Claude Code as the first harness adapter, with the layout kept in one
  `Harness` value.
- A shared `permissions` command, mounted when a host declares
  `Host.permissions`: an escalating, superset ladder of automation levels
  (`none`/`assist`/`confirm`/`full`, or `0`-`3`) where the host supplies only
  its own per-level increments and `mli` derives the grant for calling the CLI
  from the host's invocation. Prints a paste-ready block by default; `--apply`
  merges additively into `.claude/settings.local.json` (or
  `~/.claude/settings.json` with `--global`), never downgrading a rule already
  on `deny` or `ask`.
- `Host.extra_checks`, the read-side counterpart to `after_install`: a host
  returns `ExtraCheck(label, status, gates, note)` rows for per-clone state
  `mli` cannot derive (a registered pre-commit hook, say), they print in the
  shared `install --check` table, and only the rows that say they gate fold
  into the exit code — so a host with extra state keeps the shared table
  instead of writing its own `install` command.
- `mli.run` (and `mli.LOCATION_ENV`): a subprocess helper pinned to an explicit
  repo root with git's location variables (`GIT_DIR` and friends) stripped, so
  a host's `after_install` hook cannot have its shell-outs redirected at another
  repository by an inherited environment variable.
- Skill sources may be stored in the Agent Skills spec's own layout —
  `<name>/SKILL.md` — so a host's `prompts/` tree passes a skills linter as it
  stands. A source named exactly `SKILL.md` takes its name from its parent
  directory; any other file keeps naming itself by its stem, so flat sources
  are unchanged and the two layouts may be mixed. See
  [docs/source-layout.md](docs/source-layout.md).
- `Skill.name` is validated against the spec's `name` grammar at construction:
  1-64 characters of `a-z`, `0-9`, and hyphens, with no leading, trailing, or
  consecutive hyphen. `Doc.name` is deliberately exempt, since a doc is never
  installed as a skill and may namespace itself with `/`.

### Changed

- `install --check` reports a new `stale` status and gates on it: a per-repo
  copy of a kind the harness loads from *both* bases (rules and agents under
  Claude Code) is drift once a resolved global install serves the repo,
  whatever its content says — it is an extra file live in context, so the
  verdict outranks both `ok` and `drifted` and the remedy printed is `remove:`,
  never a reinstall that would recreate the file. Skills
  are unaffected, since a global skill shadows the local stub rather than
  loading alongside it, and a global copy is never flagged during a local
  install.
- `Harness` declares that discipline per kind (`shadowed_kinds`, with
  `shadows()` / `both_load()`), so it is a property of the harness rather than
  something hardcoded at the call site.
- `installed_mode` falls back to a host's other artifacts when it ships no
  skills, instead of always answering `None`.

### Deprecated

### Removed

### Fixed

### Security
