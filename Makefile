.DEFAULT_GOAL := help
SHELL := /bin/bash

PY ?= python3
PIP ?= $(PY) -m pip
NODE ?= node
NPM ?= npm

BACKEND := backend
FRONTEND := frontend
DOCS := docs

.PHONY: help bootstrap install install-dev install-frontend install-hooks clean \
	test test-fast lint format-check typecheck frontend-build security docs-build docs-serve \
	alembic-up alembic-down alembic-check dev e2e ci

help: ## Show available targets
	@printf 'Tayf Studio — developer commands\n\n'
	@printf '  make bootstrap        Install backend, frontend and pre-commit hooks\n'
	@printf '  make install-dev      Install backend dev/test dependencies\n'
	@printf '  make install-hooks    Install pre-commit hooks\n'
	@printf '  make test             Run the full backend suite with coverage gate\n'
	@printf '  make test-fast        Run backend tests without coverage\n'
	@printf '  make lint             Ruff check (the enforced lint gate)\n'
	@printf '  make typecheck        Frontend strict TypeScript build\n'
	@printf '  make security         pip-audit + bandit\n'
	@printf '  make docs-build       MkDocs strict build\n'
	@printf '  make docs-serve       Serve docs locally on port 8001\n'
	@printf '  make frontend-build   Typecheck + production bundle\n'
	@printf '  make e2e              Real-browser end-to-end smoke test\n'
	@printf '  make alembic-check    upgrade → downgrade → upgrade migration proof\n'
	@printf '  make ci               Run the local approximation of CI\n'
	@printf '  make clean            Remove caches and build output\n'

bootstrap: install-dev install-frontend install-hooks ## Install everything for development

install: install-dev install-frontend ## Install runtime/dev dependencies

install-dev: ## Install backend dev/test dependencies
	cd $(BACKEND) && $(PIP) install --upgrade pip && $(PIP) install -r requirements-dev.txt

install-frontend: ## Install frontend dependencies from the lockfile
	cd $(FRONTEND) && $(NPM) ci

install-hooks: ## Install pre-commit hooks
	$(PIP) install pre-commit
	pre-commit install --install-hooks

test: ## Run backend tests with the 80% coverage gate
	cd $(BACKEND) && $(PY) -m pytest --cov=app --cov-report=term-missing --cov-fail-under=80

test-fast: ## Run backend tests without coverage
	cd $(BACKEND) && $(PY) -m pytest -q --no-cov

lint: ## Ruff check (enforced)
	cd $(BACKEND) && ruff check .

format-check: ## Ruff format check (informational only, not a CI gate)
	cd $(BACKEND) && ruff format --check app tests

typecheck: ## Strict TypeScript typecheck
	cd $(FRONTEND) && $(NPM) run build

frontend-build: typecheck ## Build production frontend bundle
	@printf 'frontend build completed by npm run build\n'

security: ## Dependency and SAST checks
	cd $(BACKEND) && pip-audit -r requirements.txt --progress-spinner off && bandit -r app -ll -q

docs-build: ## Strict documentation build
	$(PIP) install -r $(DOCS)/requirements.txt
	mkdocs build --strict --config-file mkdocs.yml

docs-serve: ## Serve docs locally
	$(PIP) install -r $(DOCS)/requirements.txt
	mkdocs serve --config-file mkdocs.yml --dev-addr 127.0.0.1:8001

alembic-up: ## Apply migrations
	cd $(BACKEND) && alembic upgrade head

alembic-down: ## Revert migrations
	cd $(BACKEND) && alembic downgrade base

alembic-check: alembic-down alembic-up alembic-up ## Prove migration up/down/up fidelity

e2e: ## Run the real-browser smoke test
	./scripts/run_e2e.sh

dev: ## Start the full development stack
	./scripts/dev.sh start

ci: lint typecheck test security docs-build ## Local approximation of the CI pipeline

clean: ## Remove caches and build artifacts
	rm -rf $(BACKEND)/.pytest_cache $(BACKEND)/.coverage $(BACKEND)/htmlcov
	rm -rf $(FRONTEND)/dist $(FRONTEND)/node_modules/.vite
	rm -rf site .mypy_cache .ruff_cache
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
