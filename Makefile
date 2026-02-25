SCRIPT      := jackett-search
INSTALL_DIR := /usr/local/bin
INSTALL_PATH := $(INSTALL_DIR)/$(SCRIPT)

.DEFAULT_GOAL := help

.PHONY: help install uninstall lint lint-py lint-md dev-deps

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
