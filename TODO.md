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
- [ ] **Test suite** — unit tests for `parse_sort_spec`, `make_comparator`,
  `format_size`, and the config loader.
- [ ] **Configurable default sort** — allow `default_sort` to be set in the
  config file so users don't have to pass `--sort` every time.
