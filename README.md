# jackett-search

`jackett-search` searches configured Jackett indexers from the command line and
interactive terminal interface. It prints sortable results, JSON, and magnet
links, and can send magnet actions to supported download clients such as
put.io and Bitport.io.

## Table of Contents

- [Overview](#overview)
- [Usage](#usage)
- [Examples](#examples)
- [Documentation](#documentation)
- [License](#license)

## Overview

The app connects to a local Jackett instance. Install and configure Jackett and
`jackett-search` first, then use the command line or interactive mode to search
and choose where supported magnet downloads should be sent.

## Usage

```sh
jackett-search --interactive
jackett-search --indexer 1337x,yts "<placeholder>"
jackett-search --interactive --indexer 1337x,yts
```

Use `--indexer IDS` to search only the listed configured Jackett indexer IDs.
The selection applies to every search in an interactive session. Whitespace
is trimmed and duplicate IDs are queried once. Empty components, unknown IDs,
or unavailable indexer discovery cause an error before any torrent search.
Omit the flag to search all indexers with the existing discovery fallback.
Replace `<placeholder>` with your query and use IDs configured in your Jackett.

After searching, press `/` to filter loaded results by title or tracker as you
type. Press Enter to keep the filter and navigate with arrows, PageUp/PageDown,
or Home/End. Press `/` again to edit, Esc to undo the edit, or Ctrl-U to clear
the filter. Filtering is case-insensitive literal text and makes no new
Jackett requests. Results with the same non-empty info hash are combined after
sorting, with contributing indexers shown in the tracker column. See
[interactive navigation](docs/usage.md#navigation) for all keys and
[JSON output fields](docs/usage.md#json-output-fields) for output details.

Use `--category VALUE` with one non-empty Jackett category name or ID (for
example, `TV`, `Movies`, or `2000`). The value is passed verbatim as `Category[]`
to every indexer, including the `/all` fallback. It applies to every search in
an interactive session and has no in-session editor. Omitting it preserves the
default requests. The client does not look up categories or filter results by
category locally. See `jackett-search --help` for all options.

## Examples

```sh
jackett-search --category TV "Example series"
jackett-search --category 2000 --json "Example movie"
jackett-search --interactive --category Movies
```

## Documentation

| Guide | Read this for |
| --- | --- |
| [Installation and services](docs/installation.md) | Prerequisites, config file, installation, Jackett, FlareSolverr, and service commands |
| [Search and interactive mode](docs/usage.md) | CLI flags, sorting, interactive navigation, download clients, and JSON output |
| [Bitport.io setup](docs/bitport.md) | Registering a Bitport app, entering credentials, and authorizing an account |
| [Development and reference](docs/development.md) | Architecture notes, development commands, and license |

Start with [Installation and services](docs/installation.md) to create the
configuration file and connect the app to Jackett. If you plan to use Bitport,
complete [Bitport setup](docs/bitport.md) before selecting it in the interactive
client picker.

## License

[MIT](LICENSE)
