SHELL := /bin/bash
PYTHON ?= python3
VENV ?= .venv

.PHONY: help bootstrap submodules install config-validate infra-up infra-down infra-logs agent-up agent-down agent-logs agent-status migrate dev api bot worker scheduler doctor ajil-smoke codex-smoke playwright-smoke telegram-smoke format lint typecheck test test-unit test-integration test-e2e coverage clean systemd-install systemd-start systemd-stop systemd-status

help:
	@grep -E '^[a-zA-Z_-]+:' $(MAKEFILE_LIST) | cut -d: -f1 | sort
bootstrap:
	./scripts/bootstrap.sh
submodules:
	git submodule update --init --recursive
install:
	$(PYTHON) -m pip install -e '.[dev]'
config-validate:
	PYTHONPATH=src $(PYTHON) -m telegram_codex_agent.cli config validate
infra-up:
	docker compose up -d --wait postgres redis ajil_gateway
infra-down:
	docker compose down
infra-logs:
	docker compose logs -f postgres redis ajil_gateway
agent-up:
	docker compose --profile agent up -d
agent-down:
	docker compose --profile agent stop agent-api agent-bot agent-worker
agent-logs:
	docker compose --profile agent logs -f agent-api agent-bot agent-worker
agent-status:
	docker compose --profile agent ps
migrate:
	PYTHONPATH=src alembic upgrade head
dev:
	./scripts/dev.sh
api:
	PYTHONPATH=src $(PYTHON) -m telegram_codex_agent.cli api
bot:
	PYTHONPATH=src $(PYTHON) -m telegram_codex_agent.runtime bot
worker:
	PYTHONPATH=src $(PYTHON) -m telegram_codex_agent.runtime worker
scheduler:
	PYTHONPATH=src $(PYTHON) -m telegram_codex_agent.runtime scheduler
doctor:
	./scripts/doctor.sh
ajil-smoke:
	PYTHONPATH=src $(PYTHON) -m telegram_codex_agent.cli ajil-smoke
codex-smoke:
	PYTHONPATH=src $(PYTHON) -m telegram_codex_agent.cli codex smoke
playwright-smoke:
	$(PYTHON) -c 'import playwright; print("playwright package installed")'
telegram-smoke:
	PYTHONPATH=src $(PYTHON) -m pytest -q tests_agent/test_telegram.py
format:
	$(PYTHON) -m ruff format src tests tests_agent
lint:
	$(PYTHON) -m ruff check src tests tests_agent
typecheck:
	$(PYTHON) -m mypy src
test test-unit:
	PYTHONPATH=src $(PYTHON) -m pytest -q
test-integration:
	RUN_INTEGRATION_TESTS=true PYTHONPATH=src $(PYTHON) -m pytest -q tests_agent -m integration
test-e2e:
	RUN_E2E_TESTS=true PYTHONPATH=src $(PYTHON) -m pytest -q tests_agent -m e2e
coverage:
	PYTHONPATH=src $(PYTHON) -m pytest --cov=telegram_codex_agent --cov-report=xml --cov-report=term-missing
clean:
	$(PYTHON) -m ruff clean
systemd-install:
	./scripts/systemd_install.sh
systemd-start:
	systemctl --user start telegram-codex-agent-api telegram-codex-agent-bot telegram-codex-agent-worker
systemd-stop:
	systemctl --user stop telegram-codex-agent-api telegram-codex-agent-bot telegram-codex-agent-worker
systemd-status:
	systemctl --user status telegram-codex-agent-api telegram-codex-agent-bot telegram-codex-agent-worker
