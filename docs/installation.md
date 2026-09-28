# Installation and services

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

[bitport]
client_id = ""
client_secret = ""
```

Leave the Bitport fields empty until you register an app. The
[Bitport setup guide](bitport.md) explains manual entry and the interactive
`--bitport-auth` credential prompt.

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
`make uninstall` with the same installation overrides to remove the launcher
and runtime files. Ensure
`~/.local/bin` is on your `PATH`.

The install location is configurable with one prefix parameter:

```sh
# Default: ~/.local/bin and ~/.local/lib/jackett-search
make install

# A different user-owned prefix
make install INSTALL_PREFIX="$HOME/apps"
make uninstall INSTALL_PREFIX="$HOME/apps"
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
docker network inspect jackett-search >/dev/null 2>&1 \
  || docker network create jackett-search
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
http://127.0.0.1:9117/
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
docker network inspect jackett-search >/dev/null 2>&1 \
  || docker network create jackett-search
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
