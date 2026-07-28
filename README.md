# jackett-search

A fast CLI tool that queries a local [Jackett](https://github.com/Jackett/Jackett)
instance and prints torrent search results to stdout — with colour, clickable
links, flexible sorting, JSON output, and an optional dependency-free
interactive terminal interface.

## Table of Contents

- [Why](#why)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Jackett Setup](#jackett-setup)
- [FlareSolverr Setup](#flaresolverr-setup)
- [Service Control](#service-control)
- [Usage](#usage)
- [Interactive mode](#interactive-mode)
- [JSON output fields](#json-output-fields)
- [Using with an AI agent](#using-with-an-ai-agent)
- [How it works](#how-it-works)
- [Notes](#notes)
- [Development](#development)
- [License](#license)

## Why

[torrra](https://torrra.readthedocs.io) is a great TUI torrent client, but it
has no non-interactive mode. If you want to search from a script, pipe results
to `jq`, or feed them to an AI agent, you need direct access to the Jackett
API. `jackett-search` does exactly that.

## Prerequisites

| Requirement | Version | Install |
| --- | --- | --- |
| Python | 3.8+ | `brew install python` |
| Jackett | any | `brew install jackett` or `make install-jackett` |
| Docker Desktop | current | `brew install --cask docker` |
| put.io CLI | optional, interactive transfers | `brew install putdotio/tap/putio-cli` |

No external Python packages are required — the script uses the standard library only.

## Installation

### 1 — Choose how to run Jackett

You can run Jackett either:

- natively on macOS with Homebrew
- in Docker with the bundled `jackett-compose.yml`

Both are supported by `jackett-search`, because the CLI only talks to Jackett's
HTTP API at the configured `url`.

### 2 — Create the config file

`jackett-search` looks for its config in these locations (first match wins):

1. `~/.config/jackett-search/config.toml` — recommended (XDG, works on macOS and Linux)
2. `~/Library/Application Support/jackett-search/config.toml` — macOS convention
3. `~/Library/Application Support/torrra/config.toml` — legacy fallback if you already use torrra

Find your Jackett API key from whichever Jackett instance you are using.

For a Homebrew Jackett install:

```sh
grep APIKey ~/Library/Application\ Support/Jackett/ServerConfig.json
```

For the Docker Jackett install provided by this repo:

```sh
grep APIKey ~/.config/jackett-search/jackett-config/Jackett/ServerConfig.json
```

Create the config file:

```sh
mkdir -p ~/.config/jackett-search
```

Edit `~/.config/jackett-search/config.toml`:

```toml
url     = "http://127.0.0.1:9117"
api_key = "<your-jackett-api-key>"
```

### 3 — Install jackett-search

```sh
git clone https://github.com/marcomc/jackett-search.git
cd jackett-search
make install
```

`make install` creates a standalone runtime, not a link back to this checkout:

```text
~/.local/lib/jackett-search/jackett-search
~/.local/lib/jackett-search/interactive.py
~/.local/bin/jackett-search -> ~/.local/lib/jackett-search/jackett-search
```

You may move or delete the source checkout after installation. Rerun
`make install` from a newer checkout to upgrade the installed runtime; use
`make uninstall` to remove the launcher and runtime files. Ensure
`~/.local/bin` is on your `PATH`.

The install location is configurable with one prefix parameter:

```sh
# Default: ~/.local/bin and ~/.local/lib/jackett-search
make install

# A different user-owned prefix
make install INSTALL_PREFIX="$HOME/apps"
```

`INSTALL_DIR` and `INSTALL_LIB_DIR` remain available as independent overrides
for an unusual layout.

During `make install`, `jackett-search` now checks whether the bundled Docker
Compose files are already present in `~/.config/jackett-search/`. In an
interactive terminal it offers to install:

- FlareSolverr via `make install-flaresolverr`
- Jackett via `make install-jackett`

The FlareSolverr installer:

- installs `flaresolverr-compose.yml` into `~/.config/jackett-search/`
- creates the shared `jackett-search` Docker network when Docker is running
- prints the manual start command
- starts FlareSolverr immediately when Docker is already running
- otherwise tells you to start Docker Desktop first and rerun the printed command

The Jackett installer:

- installs `jackett-compose.yml` into `~/.config/jackett-search/`
- creates persistent Docker config/download directories under `~/.config/jackett-search/`
- copies an existing native macOS Jackett config into the Docker config directory the first time, excluding `._*` and `.DS_Store` metadata
- rewrites Jackett's FlareSolverr URL to `http://flaresolverr:8191` through the shared Docker network
- rewrites Jackett's bind address to `0.0.0.0` so the Docker-published port is reachable from the host
- pulls the latest Jackett image before starting it
- prints the manual start command with the required environment variables
- starts Jackett immediately when Docker is already running
- otherwise tells you to start Docker Desktop first and rerun the printed command

You can run the FlareSolverr setup directly at any time:

```sh
make install-flaresolverr
```

That installs this Compose file:

```text
~/.config/jackett-search/flaresolverr-compose.yml
```

and starts it with:

```sh
docker compose -f ~/.config/jackett-search/flaresolverr-compose.yml up -d
```

The bundled FlareSolverr service uses Docker's `unless-stopped` restart policy,
so once Docker Desktop is running again it will come back automatically.
The bundled Compose files also use distinct Compose project names, so managing
Jackett does not produce orphan-container warnings for FlareSolverr and vice versa.
They join the persistent `jackett-search` network, where Docker DNS resolves
the FlareSolverr service as `flaresolverr` on both macOS and Linux.
If you previously used an older revision of this repo that created plain
`jackett` or `flaresolverr` containers, the installers remove those legacy
containers before starting the Compose-managed services.

### Updating an existing Docker installation

`make install` preserves existing Compose files. To replace them with the
current bundled definitions, run these commands in order:

```sh
make install-flaresolverr
make install-jackett
```

They create the shared network, rewrite the Jackett endpoint, remove macOS
metadata sidecars, and restart the services. These commands intentionally
replace the installed companion Compose files. Keep a copy first if you have
made local changes to them.

Or manually:

```sh
install -d ~/.local/lib/jackett-search ~/.local/bin
install -m 755 jackett-search ~/.local/lib/jackett-search/jackett-search
install -m 644 interactive.py ~/.local/lib/jackett-search/interactive.py
ln -sf ~/.local/lib/jackett-search/jackett-search ~/.local/bin/jackett-search
```

For a system-wide installation, choose the prefix explicitly:

```sh
sudo make install INSTALL_PREFIX=/usr/local
```

### 4 — Configure Jackett to use FlareSolverr

Installing the FlareSolverr container is only half of the setup. Jackett does
not auto-discover it. You must also configure Jackett's server settings to use
the local FlareSolverr API endpoint.

Open Jackett WebUI and set the FlareSolverr URL according to how Jackett is running.

For native Homebrew Jackett:

```text
http://127.0.0.1:8191
```

For Docker Jackett installed with this repo:

```text
http://flaresolverr:8191
```

Then click:

```text
Apply server settings
```

If you skip `Apply server settings`, Jackett keeps using the previous value and
indexer tests will still fail with "FlareSolverr is not configured" errors.

## Jackett Setup

### Why Docker Jackett is now bundled

Running Jackett in Docker is optional, but it is useful when:

- you want the latest Jackett image without managing a Homebrew service
- you want Docker to restart Jackett automatically with Docker Desktop
- you want Jackett and FlareSolverr to follow the same Docker-based workflow
- you want to test or switch away from a native install without rebuilding anything

The native Homebrew install remains valid. `jackett-search` works with either
mode as long as `config.toml` points at the correct Jackett URL.

### Native Homebrew setup

If you prefer a native install:

```sh
brew install jackett
brew services start jackett
```

Jackett will be available at:

```text
http://127.0.0.1:9117
```

### Automatic Docker setup

To install Docker Jackett directly:

```sh
make install-jackett
```

This installs:

```text
~/.config/jackett-search/jackett-compose.yml
```

and persists Jackett data in:

```text
~/.config/jackett-search/jackett-config
~/.config/jackett-search/jackett-downloads
```

The active Jackett app config lives inside:

```text
~/.config/jackett-search/jackett-config/Jackett
```

On first install, if a native macOS Jackett config already exists at
`~/Library/Application Support/Jackett`, the installer copies it into the
Docker config directory so your existing API key, indexers, and settings come
across.

When that migration copies a native `ServerConfig.json`, `make install-jackett`
also rewrites `LocalBindAddress` to `0.0.0.0`. This is required in Docker,
because a native macOS value such as `127.0.0.1` makes Jackett listen only on
the container loopback, while an empty value is rejected by current Jackett
builds as `Invalid url: 'http://:9117/'`. Using `0.0.0.0` keeps
`http://127.0.0.1:9117` reachable from the host through Docker's published
port.

The migration excludes macOS AppleDouble (`._*`) and Finder (`.DS_Store`)
metadata. They are not Jackett configuration and can corrupt its .NET key ring
when copied into `DataProtection`.

### Manual Docker setup

If you want to start Docker Jackett manually after installation, run:

```sh
docker network inspect jackett-search >/dev/null 2>&1 \
  || docker network create jackett-search

PUID="$(id -u)" \
PGID="$(id -g)" \
TZ="${TZ:-UTC}" \
JACKETT_CONFIG_DIR="$HOME/.config/jackett-search/jackett-config" \
JACKETT_DOWNLOADS_DIR="$HOME/.config/jackett-search/jackett-downloads" \
docker compose -f "$HOME/.config/jackett-search/jackett-compose.yml" up -d
```

`make install-jackett` runs the equivalent command automatically when Docker is
already running, and pulls the latest Jackett image first.

### Automatic restart behavior

The bundled Jackett Compose file also uses Docker's `restart: unless-stopped`
policy. Once Docker Desktop starts again, Docker will restart the Jackett
container automatically unless you manually stopped it.

### Verification

To confirm Docker Jackett is up:

```sh
docker compose -f ~/.config/jackett-search/jackett-compose.yml ps
docker compose -f ~/.config/jackett-search/jackett-compose.yml logs --tail=100
```

Then open:

```text
http://127.0.0.1:9117/UI/
```

If you are switching from a Homebrew Jackett install, stop the native service
first so port `9117` is free:

```sh
brew services stop jackett
```

## FlareSolverr Setup

### Why this is needed

Some Jackett indexers are protected by Cloudflare or similar challenge pages.
When Jackett reports an error such as:

```text
Challenge detected but FlareSolverr is not configured
```

the indexer request is being blocked before Jackett can fetch results.
FlareSolverr runs a browser-based challenge solver that Jackett can call for
those protected indexers.

This repository now ships a ready-to-use Docker Compose file so macOS users can
install and run FlareSolverr without building anything manually.

### Automatic setup

The simplest path is:

```sh
make install
```

If `~/.config/jackett-search/flaresolverr-compose.yml` is not already present,
the installer asks whether it should install it. If you answer `yes`, it runs
`make install-flaresolverr`.

That target:

- copies the bundled Compose file into `~/.config/jackett-search/`
- prints the exact manual `docker compose` start command
- starts FlareSolverr immediately if Docker is already running
- otherwise tells you to start Docker Desktop first and rerun the printed command

### Manual setup

If you prefer to install FlareSolverr separately from `make install`, run:

```sh
make install-flaresolverr
```

This installs:

```text
~/.config/jackett-search/flaresolverr-compose.yml
```

Then either let the target start it automatically, or start it yourself:

```sh
docker compose -f ~/.config/jackett-search/flaresolverr-compose.yml up -d
```

If Docker Desktop is not running, start Docker Desktop first and then run the
same command.

## Service Control

Once FlareSolverr and Jackett compose files are installed, you can restart
services without reinstalling files:

```sh
make up
make up-flaresolverr
make up-jackett
make down
make down-flaresolverr
make down-jackett
make ps
make ps-flaresolverr
make ps-jackett
make logs
make logs-flaresolverr
make logs-jackett
```

Use cases:

- `make up` after reboot or Docker restart
- `make down` before stopping all local containers
- `make ps` for a quick operational status check
- `make logs` if a test fails after restart

If a compose file is missing, `make up-*` reports the corresponding missing
`install-*` target.

### Automatic restart behavior

The bundled Compose file uses Docker's `restart: unless-stopped` policy. That
means:

- if Docker Desktop is already running, `make install-flaresolverr` starts the container now
- if Docker Desktop starts later, Docker will bring the container back automatically
- if you manually stop the FlareSolverr container, Docker leaves it stopped until you start it again

### Verification

To confirm FlareSolverr is up:

```sh
docker compose -f ~/.config/jackett-search/flaresolverr-compose.yml ps
docker compose -f ~/.config/jackett-search/flaresolverr-compose.yml logs --tail=100
```

Then verify in Jackett WebUI that:

- the FlareSolverr URL is correct for your Jackett mode:
- native Jackett: `http://127.0.0.1:8191`
- Docker Jackett: `http://flaresolverr:8191`
- you clicked `Apply server settings`
- the affected indexer test now passes

---

## Usage

### Basic search

```sh
jackett-search "<placeholder>"
```

The table output uses **colour** and **clickable links** when run in a
supported terminal (iTerm2, Terminal.app macOS 12+, kitty, WezTerm):

- **Title** — click to open the tracker detail page in your browser
- **🧲 magnet** — click to open the magnet URI in your torrent client
- **📄 torrent** — click to download the `.torrent` file via Jackett proxy

Colour coding:

- **Seeder count** — green ≥ 100, yellow ≥ 10, dim-red < 10
- **DLF column** — `FREE` in green when `DownloadVolumeFactor = 0.0`
  (freeleech), numeric otherwise

All ANSI colour and links are automatically stripped when output is piped.

### Flags

```text
jackett-search [OPTIONS] "query"

Filter:
  --magnets-only        Only show results with a magnet URI
  --torrent-only        Only show results with a .torrent download link
                        (mutually exclusive with --magnets-only)

Output:
  --interactive           Open a full-screen interactive session (TTY only)
  --json                Emit results as a JSON array
  --limit N             Cap output at N results
  --magnet N            Print just the magnet URI for result #N (1-based)
  --clear-history       Delete persisted interactive query history and exit

Sort:
  --sort FIELDS         Comma-separated sort fields (default: seeders)
                        Append :asc or :desc to override a field's default direction

Timing:
  --timeout SECS        Per-indexer socket timeout in seconds (default: 10)
                        Use 0 to wait for every indexer regardless of how long it takes
```

### Sort fields

Append `:asc` or `:desc` to any field name to override its default direction.

| Field | Alias | Jackett column | Default |
| --- | --- | --- | --- |
| `seeders` | `s` | S — Active seeders | **desc** ← best availability |
| `leechers` | `l` | L — Leechers | desc |
| `grabs` | `g` | G — Times grabbed | desc |
| `size` | | Size | desc |
| `published` | `date` | Published — Date indexed | desc (newest first) |
| `files` | `f` | F — Number of files | desc |
| `dlf` | | DLF — Download volume factor | **asc** (0 = freeleech first) |
| `ulf` | | ULF — Upload volume factor | desc |
| `tracker` | | Tracker name | asc |
| `title` | `name` | Name | asc |

### Examples

```sh
# default — most-seeded first
jackett-search "<placeholder>"

# limit to 20 results
jackett-search --limit 20 "<placeholder>"

# only results with a magnet URI
jackett-search --magnets-only "<placeholder>"

# only .torrent results, JSON output
jackett-search --torrent-only --json "<placeholder>"

# freeleech first, then most seeded
jackett-search --sort "dlf,seeders" "<placeholder>"

# smallest file first
jackett-search --sort "size:asc" "<placeholder>"

# newest indexed first
jackett-search --sort "published" "<placeholder>"

# print just the magnet URI for result #2 (pipe-ready)
jackett-search --magnets-only "<placeholder>" --magnet 2

# give slow indexers 30 s before giving up
jackett-search --timeout 30 "<placeholder>"

# combine flags
jackett-search --magnets-only --sort "dlf,seeders" --limit 10 --json "<placeholder>"
```

## Interactive mode

`--interactive` starts a dependency-free full-screen TUI for macOS and Linux
terminals with `curses` support. It requires interactive stdin and stdout, so
it cannot be piped or redirected. Normal table, JSON, and `--magnet` output
remain unchanged.

Start a session with an initial query:

```sh
jackett-search --interactive "<placeholder>"
```

Or start in the search form, which lets you edit the query, sort order, limit,
timeout, and magnet/torrent filter before searching:

```sh
jackett-search --interactive
```

`Sort` and `Filter` are selectors: use Left/Right (or Up/Down) to cycle valid
options. `Limit (results)` and `Timeout (seconds)` accept digits only; use
`↑`/`k` to increment or `↓`/`j` to decrement them. Values never fall below
zero. Leave `Limit` empty for no result cap; incrementing a blank Limit starts
at `1`.

CLI search flags provide initial values when a query is supplied:

```sh
jackett-search --interactive --magnets-only --sort "dlf,seeders" --limit 30 "<placeholder>"
```

### Navigation

Esc always presents a confirmation before cancelling an in-progress search or
leaving completed results for the search form. `Ctrl-X` presents an exit
confirmation from any TUI screen, including editable forms; `Ctrl-C` exits
immediately. Cancelling either confirmation keeps the current search unchanged.

| Key | Action |
| --- | --- |
| `↑`/`↓`, `j`/`k` | Move between result rows |
| `←`/`→`, `h`/`l` | Focus the Magnet or Torrent action |
| `PageUp`/`PageDown` | Move one page |
| `Home`/`End`, `g`/`G` | Jump to the first or last row |
| `Ctrl-U`/`Ctrl-D` | Move half a page |
| `Enter` | Choose a client and confirm the focused action |
| `c` | Copy the focused URL to the system clipboard |
| `n` | Open a new search form, preserving previous values |
| `r` | Repeat the current search |
| `?` | Show in-session help |
| `q` | Exit from the results view |
| `Ctrl-X` | Confirm exit from any TUI screen, including forms |
| `Ctrl-C` | Exit interactive mode immediately |
| `Esc` | Confirm cancellation of a running search or return to the search form |

The table uses the same title, size, numeric, DLF, and tracker column widths
and semantic colours as normal table output. Its action slots make URL support
explicit: `M magnet` and `T torrent` are available URLs, `M —` or `T —` means
that URL type is absent, and brackets mark the action selected with `←`/`→` or
`h`/`l`. The table uses a viewport sized to the terminal and redraws when the
terminal is resized.

### Search progress

While configured indexers are being discovered, the TUI displays a spinner.
Once discovery completes, its progress bar shows completed indexer requests out
of the actual configured total, including the number still outstanding. An
indexer that fails or reaches its timeout counts as complete because its request
has finished; this is request completion, not an estimate of result quality.

### Download clients

The client picker exposes only commands available on `PATH`:

- **put.io** — shown when the `putio` CLI is installed. It accepts both Magnet
  and Torrent URLs.
- **System default application** — `open` on macOS or `xdg-open` on Linux.

Every client action requires confirmation. For put.io, the destination picker
discovers visible folders recursively from the live account, always includes
`Root`, supports incremental filtering, and displays nested folders as paths.
The transfer is submitted with an argument list equivalent to:

```sh
putio transfers add --url "<selected-url>" --save-parent-id "<folder-id>" --output json
```

When put.io returns a transfer ID, the TUI immediately offers `c` to cancel
that transfer. This is an undo after submission; cancelling at the confirmation
screen prevents submission entirely.

### Interactive preferences and history

Interactive settings live in the active `config.toml`, without duplicating the
Jackett API key:

```toml
[interactive]
persist_query_history = true
history_limit = 50
last_client = "putio"

[interactive.clients.putio]
last_folder_id = 1536595029
```

`last_client` and `last_folder_id` are written after successful actions. The
folder ID is revalidated against the live put.io folder list before use; if it
no longer exists, `Root` is selected instead.

Search history is saved beside the active config as `history.json`, with mode
`0600`. It contains only query form settings—never the Jackett API key, Magnet
URLs, result data, or transfer IDs. Set `persist_query_history = false` to keep
history only for the current TUI session. Clear saved history at any time:

```sh
jackett-search --clear-history
```

Future work for configurable third-party clients and explicit multi-result
batch submission is tracked in [`TODO.md`](TODO.md).

### JSON output fields

```sh
jackett-search --json "<placeholder>" | jq '.[].magnet_uri'
jackett-search --json "<placeholder>" | jq '.[] | select(.seeders > 100)'
```

| Field | Description |
| --- | --- |
| `title` | Torrent name |
| `tracker` | Jackett indexer that returned the result |
| `size` / `size_bytes` | Human-readable size and raw bytes |
| `seeders` | Active seeders (S) |
| `leechers` | Leechers (L) |
| `grabs` | Times grabbed from tracker (G) |
| `files` | Number of files in the torrent (F) |
| `download_volume_factor` | Download ratio cost — 0 = freeleech (DLF) |
| `upload_volume_factor` | Upload ratio credit (ULF) |
| `magnet_uri` | Full magnet link (`null` if torrent-only) |
| `info_hash` | SHA-1 info hash |
| `link` | Jackett proxy URL for the `.torrent` file |
| `details` | Tracker detail page URL |
| `category` | Tracker category string |
| `published` | ISO 8601 timestamp from the indexer |

---

## Using with an AI agent

`jackett-search --json` pairs naturally with AI assistants to select the
best torrent without manually scanning dozens of results.

### Workflow

**Step 1 — search and capture results:**

```sh
jackett-search --json --magnets-only "<placeholder>" > results.json
```

**Step 2 — ask your AI assistant to pick the best one:**

> "Here are torrent search results in JSON format.
> I want the best quality 1080p WEB-DL version of `<placeholder>`,
> preferably x265 encoded, with as many seeders as possible.
> Return only the `magnet_uri` of your recommendation."

The AI will analyse `title`, `seeders`, `size`, `category`, and `tracker`
fields and return the magnet link directly.

**Step 3 — open the magnet in your torrent client:**

```sh
open "magnet:?xt=urn:btih:..."    # macOS — opens in default torrent app
```

### One-liner shortcut

If you already know you want result #1 after sorting by seeders:

```sh
jackett-search --magnets-only "<placeholder>" --magnet 1 | pbcopy
```

This copies the magnet URI straight to your clipboard.

---

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

See [AGENTS.md](AGENTS.md) for contributor and AI-agent coding guidelines.

---

## License

[MIT](LICENSE)
