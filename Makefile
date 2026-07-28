SCRIPT      := jackett-search
PYTHON_SOURCES := $(SCRIPT) interactive.py tests
INSTALL_PREFIX ?= $(HOME)/.local
INSTALL_DIR ?= $(INSTALL_PREFIX)/bin
INSTALL_PATH := $(INSTALL_DIR)/$(SCRIPT)
INSTALL_LIB_DIR ?= $(INSTALL_PREFIX)/lib/jackett-search
INSTALL_LIB_PARENT := $(dir $(INSTALL_LIB_DIR))
INSTALL_SCRIPT_PATH := $(INSTALL_LIB_DIR)/$(SCRIPT)
INSTALL_INTERACTIVE_PATH := $(INSTALL_LIB_DIR)/interactive.py
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
DOCKER_NETWORK := jackett-search
JACKETT_START_CMD := docker compose -f "$(JACKETT_COMPOSE_DST)" up -d
USER_ID := $(shell id -u)
GROUP_ID := $(shell id -g)
TIMEZONE := $(or $(TZ),UTC)
DOCKER_JACKETT_ENV := PUID=$(USER_ID) PGID=$(GROUP_ID) TZ=$(TIMEZONE) JACKETT_CONFIG_DIR="$(JACKETT_DATA_DIR)" JACKETT_DOWNLOADS_DIR="$(JACKETT_DOWNLOADS_DIR)"
DOCKER_NETWORK_SETUP_CMD := docker network inspect $(DOCKER_NETWORK) >/dev/null 2>&1 || docker network create $(DOCKER_NETWORK)
FLARESOLVERR_MANUAL_START_CMD := $(DOCKER_NETWORK_SETUP_CMD); $(FLARESOLVERR_START_CMD)
JACKETT_MANUAL_START_CMD := $(DOCKER_NETWORK_SETUP_CMD); $(DOCKER_JACKETT_ENV) $(JACKETT_START_CMD)

# This is deliberately a shell block rather than a recursive make call so
# `make -n` stays side-effect free for install and service targets.
define ENSURE_JACKETT_NETWORK
if docker network inspect "$(DOCKER_NETWORK)" >/dev/null 2>&1; then \
	echo "✓ Shared Docker network already exists → $(DOCKER_NETWORK)"; \
elif docker network create "$(DOCKER_NETWORK)" >/dev/null; then \
	echo "✓ Created shared Docker network → $(DOCKER_NETWORK)"; \
elif docker network inspect "$(DOCKER_NETWORK)" >/dev/null 2>&1; then \
	echo "✓ Shared Docker network was created concurrently → $(DOCKER_NETWORK)"; \
else \
	echo "✗ Cannot create shared Docker network $(DOCKER_NETWORK)."; \
	exit 1; \
fi;
endef

.DEFAULT_GOAL := help

.PHONY: help \
	install install-flaresolverr install-jackett \
	ensure-jackett-network \
	uninstall \
	up up-flaresolverr up-jackett \
	down down-flaresolverr down-jackett \
	ps ps-flaresolverr ps-jackett \
	logs logs-flaresolverr logs-jackett \
	lint lint-py lint-md test dev-deps

help: ## Show available commands
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

install: ## Install standalone jackett-search for the current user
	@command -v python3 >/dev/null 2>&1 \
		|| { echo "✗ python3 not found — install Python 3.8+ first"; exit 1; }
	@python3 -c "import sys; sys.exit(0 if sys.version_info >= (3,8) else 1)" \
		|| { echo "✗ Python 3.8+ required (found $$(python3 --version))"; exit 1; }
	@staging_dir=""; backup_dir=""; failed_dir=""; \
	fail_install() { \
		echo "✗ Cannot install in $(INSTALL_DIR)."; \
		echo "  Use a writable INSTALL_DIR, or run: sudo make install INSTALL_PREFIX=/usr/local"; \
		exit 1; \
	}; \
	if ! mkdir -p "$(INSTALL_DIR)" "$(INSTALL_LIB_PARENT)"; then fail_install; fi; \
	if ! staging_dir=$$(mktemp -d "$(INSTALL_LIB_PARENT).jackett-search.install.XXXXXX"); then fail_install; fi; \
	if ! install -m 755 "$(SCRIPT)" "$$staging_dir/$(SCRIPT)" \
		|| ! install -m 644 interactive.py "$$staging_dir/interactive.py"; then \
		rm -rf "$$staging_dir"; \
		fail_install; \
	fi; \
	if [ -e "$(INSTALL_LIB_DIR)" ]; then \
		if ! backup_dir=$$(mktemp -d "$(INSTALL_LIB_PARENT).jackett-search.backup.XXXXXX"); then \
			rm -rf "$$staging_dir"; fail_install; \
		fi; \
		if ! rmdir "$$backup_dir" || ! mv "$(INSTALL_LIB_DIR)" "$$backup_dir"; then \
			rm -rf "$$staging_dir" "$$backup_dir"; fail_install; \
		fi; \
	fi; \
	if mv "$$staging_dir" "$(INSTALL_LIB_DIR)" \
		&& ln -sfn "$(INSTALL_SCRIPT_PATH)" "$(INSTALL_PATH)"; then \
		if [ -n "$$backup_dir" ]; then rm -rf "$$backup_dir"; fi; \
	else \
		if [ -e "$(INSTALL_LIB_DIR)" ]; then \
			failed_dir="$$staging_dir.failed"; \
			mv "$(INSTALL_LIB_DIR)" "$$failed_dir" || true; \
		fi; \
		if [ -n "$$backup_dir" ]; then mv "$$backup_dir" "$(INSTALL_LIB_DIR)" || true; fi; \
		if [ -d "$$staging_dir" ]; then rm -rf "$$staging_dir"; fi; \
		if [ -n "$$failed_dir" ]; then rm -rf "$$failed_dir"; fi; \
		fail_install; \
	fi
	@echo "✓ Installed standalone runtime → $(INSTALL_LIB_DIR)"
	@echo "✓ Installed launcher → $(INSTALL_PATH)"
	@echo "  Run: $(SCRIPT) --help"
	@if [ -f "$(FLARESOLVERR_COMPOSE_DST)" ]; then \
		echo "✓ FlareSolverr compose file already installed → $(FLARESOLVERR_COMPOSE_DST)"; \
	elif [ -t 0 ]; then \
		printf "Install FlareSolverr Docker Compose file in $(CONFIG_DIR)? [y/N] "; \
		read -r answer; \
		case "$$answer" in \
			[yY]|[yY][eE][sS]) make --no-print-directory install-flaresolverr ;; \
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
			[yY]|[yY][eE][sS]) make --no-print-directory install-jackett ;; \
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
	@echo "    $(FLARESOLVERR_MANUAL_START_CMD)"
	@if docker info >/dev/null 2>&1; then \
		$(ENSURE_JACKETT_NETWORK) \
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
		echo "  $(FLARESOLVERR_MANUAL_START_CMD)"; \
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
				COPYFILE_DISABLE=1 cp -R "$(JACKETT_NATIVE_CONFIG_DIR)/$$item" "$(JACKETT_APP_DIR)"; \
			fi; \
		done; \
		find "$(JACKETT_NATIVE_CONFIG_DIR)" -maxdepth 1 -type f -name 'log.txt*' -exec cp {} "$(JACKETT_APP_DIR)" \; ; \
		echo "✓ Migrated existing Jackett config from $(JACKETT_NATIVE_CONFIG_DIR)"; \
	fi
	@if [ -f "$(JACKETT_DATA_DIR)/ServerConfig.json" ]; then \
		for item in DataProtection Indexers ServerConfig.json; do \
			if [ -e "$(JACKETT_DATA_DIR)/$$item" ]; then \
				rm -rf "$(JACKETT_APP_DIR)/$$item"; \
				COPYFILE_DISABLE=1 cp -R "$(JACKETT_DATA_DIR)/$$item" "$(JACKETT_APP_DIR)"; \
			fi; \
		done; \
		find "$(JACKETT_DATA_DIR)" -maxdepth 1 -type f -name 'log.txt*' -exec cp {} "$(JACKETT_APP_DIR)" \; ; \
		echo "✓ Synced legacy Docker Jackett config into $(JACKETT_APP_DIR)"; \
	fi
	@metadata_files=$$(find "$(JACKETT_APP_DIR)" -type f \( -name '._*' -o -name '.DS_Store' \) -print -delete | wc -l | tr -d ' '); \
	if [ "$$metadata_files" -gt 0 ]; then \
		echo "✓ Removed $$metadata_files macOS metadata sidecar file(s) from Jackett config"; \
	fi
	@if [ -f "$(JACKETT_SERVER_CONFIG)" ]; then \
		JACKETT_SERVER_CONFIG="$(JACKETT_SERVER_CONFIG)" python3 -c 'import json, os, pathlib; path = pathlib.Path(os.environ["JACKETT_SERVER_CONFIG"]); data = json.loads(path.read_text()); data["FlareSolverrUrl"] = "http://flaresolverr:8191"; data["LocalBindAddress"] = "0.0.0.0"; path.write_text(json.dumps(data, indent=2) + "\n")'; \
		echo "✓ Set Docker Jackett FlareSolverr URL → http://flaresolverr:8191"; \
		echo "✓ Set Docker Jackett bind address → 0.0.0.0"; \
	fi
	@echo "✓ Installed Jackett compose file → $(JACKETT_COMPOSE_DST)"
	@echo "  Manual start command:"
	@echo "    $(JACKETT_MANUAL_START_CMD)"
	@if docker info >/dev/null 2>&1; then \
		$(ENSURE_JACKETT_NETWORK) \
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
			JACKETT_SERVER_CONFIG="$(JACKETT_SERVER_CONFIG)" python3 -c 'import json, os, pathlib; path = pathlib.Path(os.environ["JACKETT_SERVER_CONFIG"]); data = json.loads(path.read_text()); data["FlareSolverrUrl"] = "http://flaresolverr:8191"; data["LocalBindAddress"] = "0.0.0.0"; path.write_text(json.dumps(data, indent=2) + "\n")'; \
			echo "✓ Set Docker Jackett FlareSolverr URL → http://flaresolverr:8191"; \
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
		echo "  $(JACKETT_MANUAL_START_CMD)"; \
	fi

ensure-jackett-network: ## Create the shared Docker network used by companion services
	@command -v docker >/dev/null 2>&1 \
		|| { echo "✗ docker not found — install Docker first"; exit 1; }
	@$(ENSURE_JACKETT_NETWORK)

up: ## Start installed Docker companion services
	@make --no-print-directory up-flaresolverr
	@make --no-print-directory up-jackett

up-flaresolverr: ## Start FlareSolverr from installed compose file
	@command -v docker >/dev/null 2>&1 \
		|| { echo "✗ docker not found — install Docker Desktop first"; exit 1; }
	@docker compose version >/dev/null 2>&1 \
		|| { echo "✗ docker compose not available — update Docker Desktop first"; exit 1; }
	@if [ ! -f "$(FLARESOLVERR_COMPOSE_DST)" ]; then \
		echo "✗ FlareSolverr compose file is not installed in $(FLARESOLVERR_COMPOSE_DST)"; \
		echo "Run: make install-flaresolverr"; \
		exit 1; \
	fi
	@if docker info >/dev/null 2>&1; then \
		$(ENSURE_JACKETT_NETWORK) \
		echo "Starting FlareSolverr..."; \
		$(FLARESOLVERR_START_CMD) >/dev/null || exit 1; \
		echo "✓ FlareSolverr started"; \
	else \
		echo "Docker service is not running."; \
		echo "Start Docker Desktop first, then run:"; \
		echo "  $(FLARESOLVERR_MANUAL_START_CMD)"; \
		exit 1; \
	fi

up-jackett: ## Start Docker Jackett from installed compose file
	@command -v docker >/dev/null 2>&1 \
		|| { echo "✗ docker not found — install Docker Desktop first"; exit 1; }
	@docker compose version >/dev/null 2>&1 \
		|| { echo "✗ docker compose not available — update Docker Desktop first"; exit 1; }
	@if [ ! -f "$(JACKETT_COMPOSE_DST)" ]; then \
		echo "✗ Jackett compose file is not installed in $(JACKETT_COMPOSE_DST)"; \
		echo "Run: make install-jackett"; \
		exit 1; \
	fi
	@if docker info >/dev/null 2>&1; then \
		$(ENSURE_JACKETT_NETWORK) \
		echo "Starting Jackett..."; \
		$(DOCKER_JACKETT_ENV) $(JACKETT_START_CMD) >/dev/null || exit 1; \
		echo "✓ Jackett started"; \
	else \
		echo "Docker service is not running."; \
		echo "Start Docker Desktop first, then run:"; \
		echo "  $(JACKETT_MANUAL_START_CMD)"; \
		exit 1; \
	fi

down: ## Stop installed Docker companion services
	@make --no-print-directory down-flaresolverr || true
	@make --no-print-directory down-jackett || true

down-flaresolverr: ## Stop FlareSolverr without removing its data
	@if [ ! -f "$(FLARESOLVERR_COMPOSE_DST)" ]; then \
		echo "FlareSolverr compose file not installed."; \
		exit 0; \
	fi
	@if [ -f "$(FLARESOLVERR_COMPOSE_DST)" ]; then \
		echo "Stopping FlareSolverr..."; \
		docker compose -f "$(FLARESOLVERR_COMPOSE_DST)" down; \
	fi

down-jackett: ## Stop Docker Jackett without removing its data
	@if [ ! -f "$(JACKETT_COMPOSE_DST)" ]; then \
		echo "Jackett compose file not installed."; \
		exit 0; \
	fi
	@if [ -f "$(JACKETT_COMPOSE_DST)" ]; then \
		echo "Stopping Jackett..."; \
		docker compose -f "$(JACKETT_COMPOSE_DST)" down; \
	fi

ps: ## Show status of installed companion services
	@make --no-print-directory ps-flaresolverr
	@make --no-print-directory ps-jackett

ps-flaresolverr: ## Show FlareSolverr compose service status
	@if [ ! -f "$(FLARESOLVERR_COMPOSE_DST)" ]; then \
		echo "FlareSolverr compose file not installed."; \
		exit 0; \
	fi
	docker compose -f "$(FLARESOLVERR_COMPOSE_DST)" ps

ps-jackett: ## Show Jackett compose service status
	@if [ ! -f "$(JACKETT_COMPOSE_DST)" ]; then \
		echo "Jackett compose file not installed."; \
		exit 0; \
	fi
	docker compose -f "$(JACKETT_COMPOSE_DST)" ps

logs: ## Show latest logs for all installed companion services
	@make --no-print-directory logs-flaresolverr
	@make --no-print-directory logs-jackett

logs-flaresolverr: ## Show FlareSolverr logs (tail=100)
	@if [ ! -f "$(FLARESOLVERR_COMPOSE_DST)" ]; then \
		echo "FlareSolverr compose file not installed."; \
		exit 0; \
	fi
	docker compose -f "$(FLARESOLVERR_COMPOSE_DST)" logs --tail=100

logs-jackett: ## Show Jackett logs (tail=100)
	@if [ ! -f "$(JACKETT_COMPOSE_DST)" ]; then \
		echo "Jackett compose file not installed."; \
		exit 0; \
	fi
	docker compose -f "$(JACKETT_COMPOSE_DST)" logs --tail=100

uninstall: ## Remove the current user's standalone jackett-search installation
	@if ( rm -f "$(INSTALL_PATH)" && rm -rf "$(INSTALL_LIB_DIR)" ) 2>/dev/null; then \
		:; \
	else \
		echo "✗ Cannot remove the installation from $(INSTALL_DIR)."; \
		echo "  Use the same INSTALL_DIR and INSTALL_LIB_DIR values used at installation."; \
		exit 1; \
	fi
	@echo "✓ Uninstalled $(INSTALL_PATH) and $(INSTALL_LIB_DIR)"

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
	ruff check $(PYTHON_SOURCES)
	ruff format --check $(PYTHON_SOURCES)

lint-md: ## Lint Markdown files with markdownlint
	@command -v markdownlint >/dev/null 2>&1 \
		|| { echo "✗ markdownlint not found — run: make dev-deps"; exit 1; }
	markdownlint *.md

test: ## Run dependency-free Python unit tests
	python3 -m unittest discover -s tests -v
