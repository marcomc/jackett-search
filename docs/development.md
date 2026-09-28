# Development and reference

## How it works

1. Reads `url` and `api_key` from the first config file found:
   `~/.config/jackett-search/config.toml`,
   `~/Library/Application Support/jackett-search/config.toml`,
   or `~/Library/Application Support/torrra/config.toml` (legacy).
2. Fetches the list of configured indexers from Jackett's Torznab API.
3. Queries **all indexers in parallel** using `ThreadPoolExecutor`.
4. Each indexer has its own per-socket timeout (`--timeout`, default 10 s);
   slow or dead indexers are silently skipped.
5. Results are merged, filtered, sorted, and printed.

---

## Notes

- Jackett's API and web UI use the **same port** (default 9117).
  No separate API port is needed.
- The Jackett API key is shown at the top of the web UI and stored in
  `~/Library/Application Support/Jackett/ServerConfig.json`.
- Config file search order: `~/.config/jackett-search/config.toml` →
  `~/Library/Application Support/jackett-search/config.toml` →
  `~/Library/Application Support/torrra/config.toml` (legacy fallback).
- Stop Jackett: `brew services stop jackett`
- Update Jackett: `brew upgrade jackett`

---

## Development

```sh
make dev-deps   # install ruff and markdownlint-cli
make lint       # run all linters
make lint-py    # Python only (ruff check + ruff format --check)
make lint-md    # Markdown only (markdownlint)
```

See [AGENTS.md](../AGENTS.md) for contributor and AI-agent coding guidelines.

---

## License

[MIT](../LICENSE)
