# AGENTS.md — Instructions for AI Agents working on this repository

## Linting — mandatory after every change

Run linting after **every** file you create or modify before considering a task done:

```sh
make lint          # run all linters (Python + Markdown)
make lint-py       # Python only  (ruff check + ruff format --check)
make lint-md       # Markdown only (markdownlint)
```

**Never silence or suppress a linting error with an inline ignore comment
unless there is a compelling technical reason.  Fix the root cause instead.**

If a rule fires that genuinely cannot be fixed (e.g. a URL that exceeds the
line-length limit inside a code block), document *why* in a comment, and
prefer adjusting `.markdownlint.yaml` or `ruff.toml` project-wide rather than
adding per-line suppression.

## Changelog — keep it current

Every feature addition, bug fix or breaking change must be recorded in
`CHANGELOG.md` under `[Unreleased]`, unless the latest concrete heading is the
pending body of an explicit release-preparation branch. In that case, add it to
that release heading using Keep a Changelog format:

- `### Added` — new features
- `### Changed` — changes to existing behaviour
- `### Fixed` — bug fixes
- `### Removed` — removed features

## README — keep it in sync

When you add a new flag, option, or behaviour to `jackett-search`:

1. Update the **Usage** section in `README.md`.
2. Update the sort-field table if sort fields change.
3. Keep the **Examples** block runnable and accurate.

## Security — never commit secrets

The Jackett API key lives in the user's config file
(`~/.config/jackett-search/config.toml` or the platform equivalent).
It must **never** appear in any file committed to git.
The `.gitignore` already excludes `config.toml` and `*.local`.

## Script conventions

- The `jackett-search` script has no external pip dependencies (stdlib only).
  Do not add third-party imports without a strong reason and updating the
  README prerequisites section.
- ANSI/OSC 8 output is guarded by `_IS_TTY = sys.stdout.isatty()`.
  Keep this guard intact; piped output must remain clean text.
- Column padding must use the pre-pad-then-colour pattern (pad visible text
  first, then wrap in ANSI) to avoid misalignment.  See `colour_seeds()` and
  `colour_dlf()` for the canonical example.

## Interactive terminal UI and installation

- Keep terminal-mode changes exception-safe: restore input settings before
  propagating cancellation, and catch `KeyboardInterrupt` outside
  `curses.wrapper` after cleanup completes.
- Treat field constraints, destructive navigation, action availability, and
  focus as explicit UI state. Printable keys remain input in editable fields;
  use a documented non-printing key plus confirmation for exit or cancellation.
- Render numeric controls with a semantic label, unit, bounds, and documented
  empty-value behavior. Progress must report concrete completed work units,
  not elapsed-time animation.
- For cancellable blocking network work, use a separately terminable process
  and verify cancellation plus renderer behavior through a pseudo-terminal.
- Default standalone installs to a configurable user-local prefix. Install all
  local runtime imports outside the source checkout, test an isolated prefix,
  and reserve system-wide installation with `sudo` for an explicit request.
- Keep `make -n` non-mutating: do not put recursive `$(MAKE)` calls inside
  install or service recipes, because GNU Make executes those recipes during a
  dry run. Cover each affected entrypoint with fake external binaries.
- Keep container service addresses topology-specific; verify DNS from the
  consumer container and exclude macOS `._` metadata sidecars from copied
  runtime configuration.
