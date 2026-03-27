SCRIPT      := jackett-search
INSTALL_DIR := /usr/local/bin
INSTALL_PATH := $(INSTALL_DIR)/$(SCRIPT)
CONFIG_DIR := $(HOME)/.config/jackett-search
FLARESOLVERR_COMPOSE_SRC := $(CURDIR)/flaresolverr-compose.yml
FLARESOLVERR_COMPOSE_DST := $(CONFIG_DIR)/flaresolverr-compose.yml
FLARESOLVERR_START_CMD := docker compose -f "$(FLARESOLVERR_COMPOSE_DST)" up -d
JACKETT_COMPOSE_SRC := $(CURDIR)/jackett-compose.yml
JACKETT_COMPOSE_DST := $(CONFIG_DIR)/jackett-compose.yml
JACKETT_DATA_DIR := $(CONFIG_DIR)/jackett-config
JACKETT_APP_DIR := $(JACKETT_DATA_DIR)/Jackett
JACKETT_DOWNLOADS_DIR := $(CONFIG_DIR)/jackett-downloads
JACKETT_NATIVE_CONFIG_DIR := $(HOME)/Library/Application Support/Jackett
JACKETT_SERVER_CONFIG := $(JACKETT_APP_DIR)/ServerConfig.json
JACKETT_START_CMD := docker compose -f "$(JACKETT_COMPOSE_DST)" up -d
USER_ID := $(shell id -u)
GROUP_ID := $(shell id -g)
TIMEZONE := $(or $(TZ),UTC)
DOCKER_JACKETT_ENV := PUID=$(USER_ID) PGID=$(GROUP_ID) TZ=$(TIMEZONE) JACKETT_CONFIG_DIR="$(JACKETT_DATA_DIR)" JACKETT_DOWNLOADS_DIR="$(JACKETT_DOWNLOADS_DIR)"

.DEFAULT_GOAL := help

.PHONY: help install install-flaresolverr install-jackett uninstall lint lint-py lint-md dev-deps

help: ## Show available commands
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

install: ## Install jackett-search to $(INSTALL_DIR) (requires Python 3.8+)
	@command -v python3 >/dev/null 2>&1 \
		|| { echo "✗ python3 not found — install Python 3.8+ first"; exit 1; }
	@python3 -c "import sys; sys.exit(0 if sys.version_info >= (3,8) else 1)" \
		|| { echo "✗ Python 3.8+ required (found $$(python3 --version))"; exit 1; }
	@chmod +x $(SCRIPT)
	@ln -sf "$(CURDIR)/$(SCRIPT)" $(INSTALL_PATH) \
		|| sudo ln -sf "$(CURDIR)/$(SCRIPT)" $(INSTALL_PATH)
	@echo "✓ Installed → $(INSTALL_PATH)"
	@echo "  Run: $(SCRIPT) --help"
	@if [ -f "$(FLARESOLVERR_COMPOSE_DST)" ]; then \
		echo "✓ FlareSolverr compose file already installed → $(FLARESOLVERR_COMPOSE_DST)"; \
	elif [ -t 0 ]; then \
		printf "Install FlareSolverr Docker Compose file in $(CONFIG_DIR)? [y/N] "; \
		read -r answer; \
		case "$$answer" in \
			[yY]|[yY][eE][sS]) $(MAKE) install-flaresolverr ;; \
			*) echo "Skipped FlareSolverr install."; ;; \
		esac; \
	else \
		echo "FlareSolverr compose file not installed."; \
		echo "Run 'make install-flaresolverr' later to install it."; \
	fi
	@if [ -f "$(JACKETT_COMPOSE_DST)" ]; then \
		echo "✓ Jackett compose file already installed → $(JACKETT_COMPOSE_DST)"; \
	elif [ -t 0 ]; then \
		printf "Install Jackett Docker Compose file in $(CONFIG_DIR)? [y/N] "; \
		read -r answer; \
		case "$$answer" in \
			[yY]|[yY][eE][sS]) $(MAKE) install-jackett ;; \
			*) echo "Skipped Jackett Docker install."; ;; \
		esac; \
	else \
		echo "Jackett compose file not installed."; \
		echo "Run 'make install-jackett' later to install it."; \
	fi

install-flaresolverr: ## Install FlareSolverr Docker Compose file in $(CONFIG_DIR)
	@command -v docker >/dev/null 2>&1 \
		|| { echo "✗ docker not found — install Docker Desktop first"; exit 1; }
	@docker compose version >/dev/null 2>&1 \
		|| { echo "✗ docker compose not available — update Docker Desktop first"; exit 1; }
	@mkdir -p "$(CONFIG_DIR)"
	@cp "$(FLARESOLVERR_COMPOSE_SRC)" "$(FLARESOLVERR_COMPOSE_DST)"
	@echo "✓ Installed FlareSolverr compose file → $(FLARESOLVERR_COMPOSE_DST)"
	@echo "  Manual start command:"
	@echo "    $(FLARESOLVERR_START_CMD)"
	@if docker info >/dev/null 2>&1; then \
		if docker inspect flaresolverr >/dev/null 2>&1; then \
			image=$$(docker inspect -f '{{.Config.Image}}' flaresolverr 2>/dev/null || true); \
			if [ "$$image" = "ghcr.io/flaresolverr/flaresolverr:latest" ]; then \
				docker rm -f flaresolverr >/dev/null; \
				echo "✓ Removed legacy FlareSolverr container to migrate to the Compose-managed service"; \
			fi; \
		fi; \
		$(FLARESOLVERR_START_CMD) || exit 1; \
		echo "✓ FlareSolverr started"; \
	else \
		echo "Docker service is not running."; \
		echo "Start Docker Desktop first, then run:"; \
		echo "  $(FLARESOLVERR_START_CMD)"; \
	fi

install-jackett: ## Install Jackett Docker Compose file in $(CONFIG_DIR)
	@command -v docker >/dev/null 2>&1 \
		|| { echo "✗ docker not found — install Docker Desktop first"; exit 1; }
	@docker compose version >/dev/null 2>&1 \
		|| { echo "✗ docker compose not available — update Docker Desktop first"; exit 1; }
	@mkdir -p "$(CONFIG_DIR)" "$(JACKETT_DATA_DIR)" "$(JACKETT_APP_DIR)" "$(JACKETT_DOWNLOADS_DIR)"
	@cp "$(JACKETT_COMPOSE_SRC)" "$(JACKETT_COMPOSE_DST)"
	@if [ ! -f "$(JACKETT_SERVER_CONFIG)" ] && [ -d "$(JACKETT_NATIVE_CONFIG_DIR)" ]; then \
		for item in DataProtection Indexers ServerConfig.json; do \
			if [ -e "$(JACKETT_NATIVE_CONFIG_DIR)/$$item" ]; then \
				cp -R "$(JACKETT_NATIVE_CONFIG_DIR)/$$item" "$(JACKETT_APP_DIR)"; \
			fi; \
		done; \
		find "$(JACKETT_NATIVE_CONFIG_DIR)" -maxdepth 1 -type f -name 'log.txt*' -exec cp {} "$(JACKETT_APP_DIR)" \; ; \
		echo "✓ Migrated existing Jackett config from $(JACKETT_NATIVE_CONFIG_DIR)"; \
	fi
	@if [ -f "$(JACKETT_DATA_DIR)/ServerConfig.json" ]; then \
		for item in DataProtection Indexers ServerConfig.json; do \
			if [ -e "$(JACKETT_DATA_DIR)/$$item" ]; then \
				rm -rf "$(JACKETT_APP_DIR)/$$item"; \
				cp -R "$(JACKETT_DATA_DIR)/$$item" "$(JACKETT_APP_DIR)"; \
			fi; \
		done; \
		find "$(JACKETT_DATA_DIR)" -maxdepth 1 -type f -name 'log.txt*' -exec cp {} "$(JACKETT_APP_DIR)" \; ; \
		echo "✓ Synced legacy Docker Jackett config into $(JACKETT_APP_DIR)"; \
	fi
	@if [ -f "$(JACKETT_SERVER_CONFIG)" ]; then \
		JACKETT_SERVER_CONFIG="$(JACKETT_SERVER_CONFIG)" python3 -c 'import json, os, pathlib; path = pathlib.Path(os.environ["JACKETT_SERVER_CONFIG"]); data = json.loads(path.read_text()); data["FlareSolverrUrl"] = "http://host.docker.internal:8191"; data["LocalBindAddress"] = "0.0.0.0"; path.write_text(json.dumps(data, indent=2) + "\n")'; \
		echo "✓ Set Docker Jackett FlareSolverr URL → http://host.docker.internal:8191"; \
		echo "✓ Set Docker Jackett bind address → 0.0.0.0"; \
	fi
	@echo "✓ Installed Jackett compose file → $(JACKETT_COMPOSE_DST)"
	@echo "  Manual start command:"
	@echo "    $(DOCKER_JACKETT_ENV) $(JACKETT_START_CMD)"
	@if docker info >/dev/null 2>&1; then \
		echo "Pulling latest Jackett image..."; \
		if docker inspect jackett >/dev/null 2>&1; then \
			image=$$(docker inspect -f '{{.Config.Image}}' jackett 2>/dev/null || true); \
			if [ "$$image" = "lscr.io/linuxserver/jackett:latest" ]; then \
				docker rm -f jackett >/dev/null; \
				echo "✓ Removed legacy Jackett container to migrate to the Compose-managed service"; \
			fi; \
		fi; \
		$(DOCKER_JACKETT_ENV) docker compose -f "$(JACKETT_COMPOSE_DST)" pull jackett || exit 1; \
		$(DOCKER_JACKETT_ENV) $(JACKETT_START_CMD) || exit 1; \
		if [ ! -f "$(JACKETT_SERVER_CONFIG)" ]; then \
			echo "Waiting for Jackett to create $(JACKETT_SERVER_CONFIG)..."; \
			for _ in 1 2 3 4 5 6 7 8 9 10; do \
				[ -f "$(JACKETT_SERVER_CONFIG)" ] && break; \
				sleep 1; \
			done; \
		fi; \
		if [ -f "$(JACKETT_SERVER_CONFIG)" ]; then \
			JACKETT_SERVER_CONFIG="$(JACKETT_SERVER_CONFIG)" python3 -c 'import json, os, pathlib; path = pathlib.Path(os.environ["JACKETT_SERVER_CONFIG"]); data = json.loads(path.read_text()); data["FlareSolverrUrl"] = "http://host.docker.internal:8191"; data["LocalBindAddress"] = "0.0.0.0"; path.write_text(json.dumps(data, indent=2) + "\n")'; \
			echo "✓ Set Docker Jackett FlareSolverr URL → http://host.docker.internal:8191"; \
			echo "✓ Set Docker Jackett bind address → 0.0.0.0"; \
			$(DOCKER_JACKETT_ENV) docker compose -f "$(JACKETT_COMPOSE_DST)" restart jackett >/dev/null || exit 1; \
		else \
			echo "✗ Jackett did not create $(JACKETT_SERVER_CONFIG)"; \
			exit 1; \
		fi; \
		echo "✓ Jackett started"; \
	else \
		echo "Docker service is not running."; \
		echo "Start Docker Desktop first, then run:"; \
		echo "  $(DOCKER_JACKETT_ENV) $(JACKETT_START_CMD)"; \
	fi

uninstall: ## Remove jackett-search from $(INSTALL_DIR)
	@rm -f $(INSTALL_PATH) 2>/dev/null \
		|| sudo rm -f $(INSTALL_PATH)
	@echo "✓ Uninstalled $(INSTALL_PATH)"

dev-deps: ## Install linting tools (ruff, markdownlint-cli)
	@command -v ruff >/dev/null 2>&1 \
		|| { echo "Installing ruff…"; pip3 install --quiet ruff; }
	@command -v markdownlint >/dev/null 2>&1 \
		|| { echo "Installing markdownlint-cli…"; brew install markdownlint-cli; }
	@echo "✓ Dev dependencies ready"

lint: lint-py lint-md ## Run all linters

lint-py: ## Lint Python source with ruff
	@command -v ruff >/dev/null 2>&1 \
		|| { echo "✗ ruff not found — run: make dev-deps"; exit 1; }
	ruff check $(SCRIPT)
	ruff format --check $(SCRIPT)

lint-md: ## Lint Markdown files with markdownlint
	@command -v markdownlint >/dev/null 2>&1 \
		|| { echo "✗ markdownlint not found — run: make dev-deps"; exit 1; }
	markdownlint *.md
