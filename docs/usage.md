# Search and interactive mode

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
at `1`. A compound sort passed on the command line is preserved for its initial
search; the first Sort-selector change switches to the first or last supported
single-field sort, according to direction.

The interactive form defaults to magnet results. Change the default for this
installation in `config.toml`:

```toml
[interactive]
default_filter = "magnets" # also accepts "both" or "torrents"
```

The Filter selector remains available for each search. A saved history entry
retains the filter used for that search.

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

On terminals wide enough for the full table, its title, size, numeric, DLF,
and tracker columns use the same widths and semantic colours as normal table
output. At the supported 80-column minimum it compacts those columns and shows
`M/T` action cells (`[M]` or `[T]` marks focus), so URL availability and the
selected action always remain visible. The table uses a viewport sized to the
terminal and redraws when the terminal is resized.

### Search progress

While configured indexers are being discovered, the TUI displays a spinner.
Once discovery completes, its progress bar shows completed indexer requests out
of the actual configured total, including the number still outstanding. An
indexer that fails or reaches its timeout counts as complete because its request
has finished; this is request completion, not an estimate of result quality.

### Download clients

The client picker exposes configured cloud services and local applications
available on `PATH`:

- **put.io** — shown when the `putio` CLI is installed for a selected Magnet
  URL. A selected Torrent URL is a Jackett retrieval link and remains available
  only to the system-default local client until torrent-payload delivery is
  implemented.
- **Bitport.io** — shown for Magnet actions when `[bitport] access_token` is
  configured. Bitport receives the magnet through its API; the destination
  picker loads the account's folders and remembers the last selected folder.
- **System default application** — `open` on macOS or `xdg-open` on Linux.

Every client action requires confirmation. For put.io, the destination picker
discovers visible folders recursively from the live account, always includes
`Root`, supports incremental filtering, and displays nested folders as paths.
While filtering, every printable key is filter text—including `j`, `k`, `q`,
`g`, and `G`; use arrows, PageUp/PageDown, Home/End, Escape, or Ctrl-X for
navigation and cancellation. The selected Magnet URL is submitted with an
argument list equivalent to:

```sh
putio transfers add --url "<selected-url>" --save-parent-id "<folder-id>" --output json
```

When put.io returns a transfer ID, the TUI immediately offers `c` to cancel
that transfer. This is an undo after submission; cancelling at the confirmation
screen prevents submission entirely. Escape during creation or cancellation
confirms whether to stop the local command; the remote service may already have
accepted that request, so check its transfer list after cancellation.

Bitport app registration, credential entry, and account authorization are
covered in the [Bitport setup guide](bitport.md).

### Interactive preferences and history

Interactive settings live in the active `config.toml`, without duplicating the
Jackett API key:

```toml
[interactive]
persist_query_history = true
history_limit = 50
default_filter = "magnets"
last_client = "putio"

[interactive.clients.putio]
last_folder_id = 123456789 # example folder ID

[interactive.clients.bitport]
last_folder_code = "abc123" # example folder code
```

`last_client` and destination identifiers are written after successful actions.
The saved `default_filter` affects new searches; restoring a history entry uses
the filter saved with that entry. Folder choices are revalidated against the
live provider folder list before use; if a saved folder is gone, `Root` is
selected instead.

Search history is saved beside the active config as `history.json`, with mode
`0600`. It contains only query form settings—never the Jackett API key, Magnet
URLs, result data, or transfer IDs. Set `persist_query_history = false` to keep
history only for the current TUI session. Clear saved history at any time:

```sh
jackett-search --clear-history
```

Future work for configurable third-party clients and explicit multi-result
batch submission is tracked in [`TODO.md`](../TODO.md).

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
