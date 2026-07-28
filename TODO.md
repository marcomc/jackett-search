# TODO

Planned improvements, roughly prioritised.

## High priority

- [ ] **Result deduplication** — collapse identical torrents returned by
  multiple indexers (match on `InfoHash`); show a merged `Trackers` list.
- [ ] **`--category` filter** — accept a Jackett category string or ID
  (e.g. `TV`, `Movies`, `2000`) and pass it as the `Category[]` query
  parameter to each indexer.

## Medium priority

- [ ] **`--indexer` flag** — query only a named subset of configured indexers
  instead of all of them (e.g. `--indexer 1337x,yts`).
- [ ] **`--open` flag** — pipe the selected magnet URI to `open` (macOS) /
  `xdg-open` (Linux) to launch it directly in the default torrent client.
- [ ] **`--output FILE`** — write JSON results to a file in addition to
  (or instead of) stdout.

## Low priority / ideas

- [ ] **Result caching** — cache JSON responses locally for a configurable
  TTL to avoid hammering indexers on repeated identical searches.
- [ ] **Colour theme option** — `--no-colour` flag to disable ANSI output
  even on a TTY (for terminals that support OSC 8 but not 256-colour).
- [x] **Core test suite** — dependency-free unit coverage for interactive
  preferences/history, client availability, put.io command construction,
  folder parsing, result-action state, CLI guardrails, sorting, formatting, and
  config loading.
- [ ] **Configurable default sort** — allow `default_sort` to be set in the
  config file so users don't have to pass `--sort` every time.
- [ ] **Configurable interactive clients** — add documented command templates
  for additional local clients such as qBittorrent, Transmission, and Deluge,
  while retaining runtime availability checks and confirmation before launch.
- [ ] **Interactive batch submission** — expose marked result rows with a
  review screen, then submit every marked result to one chosen client and one
  destination. The current result-state model already reserves marked rows for
  this extension.

## Propositions

- [ ] **Per-invocation Jackett connection overrides** — add `--url`,
  `--api-key`, and `--config` CLI options, in that priority order, so each
  invocation can select a Jackett endpoint or configuration without changing
  the default config file.
  - Define how each flag overrides values loaded from the selected config.
  - Make `--config` select the config file before applying endpoint and API-key
    overrides, while preserving the existing first-match fallback when omitted.
  - Update the README usage and examples, and add coverage for the resolution
    precedence and missing-value errors.

- [ ] **Prioritized multi-server Jackett failover** — allow the CLI to know
  about multiple Jackett servers, query them in priority order, and continue
  to the next server when the current server is unavailable or returns no
  usable data.
  - Decide whether server definitions belong in one ordered config file, in
    multiple config files, or support both without making selection ambiguous.
  - Define failure and no-data semantics, including whether results from a
    successful fallback server replace or merge with earlier partial results.
  - Keep per-server URLs and API keys isolated, and preserve safe handling of
    credentials in diagnostics and output.
  - Update the README usage and examples, and add tests for priority ordering,
    unavailable servers, empty responses, and successful fallback.

- [ ] **Localized interactive interface** — make the interactive TUI and
  user-facing CLI messages translatable while retaining English as the default.
  - Define an explicit locale-selection and fallback contract for macOS and
    Linux, without relying on third-party dependencies.
  - Move user-facing strings behind a standard-library-compatible message
    catalog or equivalent translation boundary.
  - Localize labels, prompts, confirmation panels, help, errors, units, and
    plural-sensitive result counts without changing machine-readable output.
  - Add coverage for the English fallback and at least one non-English locale.
