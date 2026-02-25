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
`CHANGELOG.md` under the `[Unreleased]` section using Keep a Changelog format:

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
