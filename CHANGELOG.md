# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- `Host` declaration: distribution name, CLI name, prompt package, and the
  skills, rules, and agents a package ships, with an `after_install` hook.
- `register(app, host)` mounts the shared grammar on a host's typer app:
  `skill`, `install`, and, when declared, `rule` and `agent`.
- Skills install as print-on-demand stubs; a multi-source skill becomes a
  dispatcher whose subcommands are the source stems. Rules and agents install
  as stamped copies.
- Global (`~/.claude/`) and local (repository) install modes, with the
  repository root found by walking up to `.git` or `.claude/`.
- One stamp format naming the host version, the `mli` version, the mode, and
  the regenerate command; `install --check` masks both versions and reports
  `ok`, `drifted`, `missing`, or `foreign` with a reason per file.
- Foreign files (unstamped, another package's stamp, symlinks, directories,
  undecodable bytes) are never replaced without `--force`, and every target
  is guarded before the first write.
- `{cli}` placeholder rendering per mode for artifacts that opt in.
- `mli hosts` and `mli check` over the `mli.hosts` entry-point group.
- `mli.testing.sandbox` and `mli.testing.wheel_files` for host test suites.
- Claude Code as the first harness adapter, with the layout kept in one
  `Harness` value.

### Changed

### Deprecated

### Removed

### Fixed

### Security
