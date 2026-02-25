# jackett-search

A fast, non-interactive CLI tool that queries a local [Jackett](https://github.com/Jackett/Jackett)
instance and prints torrent search results to stdout — with colour, clickable
links, flexible sorting, and JSON output for scripting and AI agents.

## Why

[torrra](https://torrra.readthedocs.io) is a great TUI torrent client, but it
has no non-interactive mode. If you want to search from a script, pipe results
to `jq`, or feed them to an AI agent, you need direct access to the Jackett
API. `jackett-search` does exactly that.

## Prerequisites

| Requirement | Version | Install |
| --- | --- | --- |
| Python | 3.8+ | `brew install python` |
| Jackett | any | `brew install jackett` |

No external Python packages are required — the script uses the standard library only.

## Installation

### 1 — Install and start Jackett

```sh
brew install jackett
brew services start jackett   # auto-starts on login
```

Open <http://127.0.0.1:9117/UI/> and add the indexers you want to search.

### 2 — Create the config file

`jackett-search` looks for its config in these locations (first match wins):

1. `~/.config/jackett-search/config.toml` — recommended (XDG, works on macOS and Linux)
2. `~/Library/Application Support/jackett-search/config.toml` — macOS convention
3. `~/Library/Application Support/torrra/config.toml` — legacy fallback if you already use torrra

Find your Jackett API key (it is also shown at the top of the Jackett web UI):

```sh
grep APIKey ~/Library/Application\ Support/Jackett/ServerConfig.json
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

Or manually:

```sh
chmod +x jackett-search
sudo ln -sf "$PWD/jackett-search" /usr/local/bin/jackett-search
```

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
  --json                Emit results as a JSON array
  --limit N             Cap output at N results
  --magnet N            Print just the magnet URI for result #N (1-based)

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
