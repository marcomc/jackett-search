# jackett-search

`jackett-search` searches configured Jackett indexers from the command line and
interactive terminal interface. It prints sortable results, JSON, and magnet
links, and can send magnet actions to supported download clients such as
put.io and Bitport.io.

## Table of Contents

- [Overview](#overview)
- [Usage](#usage)
- [Documentation](#documentation)
- [License](#license)

## Overview

The app connects to a local Jackett instance. Install and configure Jackett and
`jackett-search` first, then use the command line or interactive mode to search
and choose where supported magnet downloads should be sent.

## Usage

```sh
jackett-search --interactive
```

After searching, press `/` to filter loaded results by title or tracker as you
type. Press Enter to keep the filter and navigate with arrows, PageUp/PageDown,
or Home/End. Press `/` again to edit, Esc to undo the edit, or Ctrl-U to clear
the filter. Filtering is case-insensitive literal text and makes no new
Jackett requests. See [interactive navigation](docs/usage.md#navigation) for
all keys.

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
