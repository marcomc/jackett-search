# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2026-03-10

### Added

- Bundled `flaresolverr-compose.yml` for running FlareSolverr with Docker
  Compose and Docker restart policy `unless-stopped`.
- Bundled `jackett-compose.yml` for running Jackett with Docker Compose and
  Docker restart policy `unless-stopped`.
- `make install-flaresolverr` to install the bundled Compose file into
  `~/.config/jackett-search/`, print the manual start command, and start the
  container automatically when Docker is already running.
- `make install-jackett` to install the bundled Jackett Compose file, migrate
  an existing native Jackett config on first install, pull the latest Jackett
  image, and start the container automatically when Docker is already running.

### Changed

- `make install` now detects whether the FlareSolverr Compose file is already
  installed and, in interactive use, offers to install it by delegating to
  `make install-flaresolverr`.
- `make install` now also detects whether the Jackett Compose file is already
  installed and, in interactive use, offers to install it by delegating to
  `make install-jackett`.
- `make install-jackett` now rewrites migrated Jackett configs to bind Docker
  Jackett to `0.0.0.0` instead of container-local `127.0.0.1`, and avoids an
  invalid empty bind value. This fixes both the empty-response failure where
  the published WebUI and API port were unreachable from the host and the
  startup crash `Invalid url: 'http://:9117/'`.
- Bundled Jackett and FlareSolverr Compose files now use distinct Compose
  project names, avoiding orphan-container warnings when managing one service
  independently of the other.
- Installers now remove legacy fixed-name Docker containers from earlier repo
  revisions before starting the Compose-managed services, and they fail fast if
  `docker compose pull`, `up`, or `restart` fails.

## [0.1.0] - 2026-02-25

### Added

- **Non-interactive search** against a local Jackett instance — no TUI required.
- **Parallel indexer querying** using `ThreadPoolExecutor`: all configured
  indexers are queried simultaneously; slow or dead indexers are abandoned
  after a configurable per-indexer timeout instead of blocking the entire
  request.
- **`--timeout SECS`** flag — per-indexer socket timeout in seconds
  (default 10 s). Use `0` for no cut-off (wait for every indexer to reply).
- **`--limit N`** flag — cap output at N results.
- **`--magnets-only`** flag — show only results that carry a magnet URI.
- **`--torrent-only`** flag — show only results with a `.torrent` download
  link. Mutually exclusive with `--magnets-only`.
- **`--json`** flag — emit results as a JSON array for piping to `jq` or
  feeding to AI agents.
- **`--magnet N`** flag — print the raw magnet URI for result number N to
  stdout, ready to pipe or copy-paste into a torrent client.
- **`--sort FIELDS`** flag — comma-separated sort key list with optional
  `:asc`/`:desc` direction suffix per field. Default sort is `seeders`
  (most-seeded first). Supported fields: `seeders`, `leechers`, `grabs`,
  `size`, `published`, `files`, `dlf`, `ulf`, `tracker`, `title`.
- **Rich terminal table** with ANSI colour coding:
  - Seeder count: green ≥ 100, yellow ≥ 10, dim-red < 10.
  - DLF column: displays `FREE` in green when `DownloadVolumeFactor = 0.0`
    (freeleech).
  - Separator line and result count dimmed for visual hierarchy.
- **OSC 8 clickable hyperlinks** in the terminal (iTerm2, Terminal.app
  macOS 12+, kitty, WezTerm, etc.):
  - Title cell links to the tracker detail page.
  - 🧲 magnet label opens the magnet URI in the default torrent client.
  - 📄 torrent label downloads the `.torrent` file via the Jackett proxy.
- **Graceful TTY detection** — ANSI colour and OSC 8 links are suppressed
  automatically when stdout is piped; plain text is emitted instead.
- **Config auto-discovery** — reads `url` and `api_key` from the first
  config file found: `~/.config/jackett-search/config.toml` (XDG primary),
  `~/Library/Application Support/jackett-search/config.toml` (macOS
  convention), or `~/Library/Application Support/torrra/config.toml`
  (legacy fallback for existing torrra users). No torrra installation
  required.
- **`--version`** flag — print the script version and exit.
- **Makefile** with `help`, `install`, `uninstall`, `lint`, `lint-py`,
  `lint-md`, and `dev-deps` targets.
- **GitHub Actions CI** — `.github/workflows/lint.yml` runs `make lint`
  on every push and pull request.
- **`pyproject.toml`** — project metadata and ruff configuration.
- **AGENTS.md** with contributor and AI-agent coding guidelines.
- **`.markdownlint.yaml`** project-wide markdownlint configuration.
- **`.gitignore`** covering Python artefacts, macOS metadata, and local
  config files that may contain API keys.

[Unreleased]: https://github.com/marcomc/jackett-search/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/marcomc/jackett-search/releases/tag/v0.1.0
