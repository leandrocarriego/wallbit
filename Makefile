# Cierre: day-to-day commands. `make` (or `make help`) lists them all.
SHELL := /bin/bash
COMPOSE := docker compose
API := $(COMPOSE) exec api
WEB := $(COMPOSE) exec web

.DEFAULT_GOAL := help
.PHONY: help init hooks precommit e2e seed-volume up down restart build ps logs urls health clean \
        migrate migration seed shell psql rabbit \
        test test-back test-web lint fmt typecheck api-client load

help: ## List available commands
	@awk 'BEGIN {FS = ":.*## "; printf "\nUsage: make <command>\n\n"} /^[a-zA-Z_-]+:.*## / {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)
	@echo

# ---------- environment ----------
init: ## Create .env from .env.example if missing
	@test -f .env || (cp .env.example .env && echo "Created .env from .env.example")

hooks: ## Install git hooks (pre-commit, commit-msg, pre-push)
	uvx pre-commit install

precommit: ## Run every hook on the whole repo
	uvx pre-commit run --all-files

up: init ## Start everything (data, API, workers, web, observability)
	$(COMPOSE) up -d --build --renew-anon-volumes
	@$(MAKE) --no-print-directory urls

down: ## Stop services (keeps data)
	$(COMPOSE) down

restart: ## Restart a service: make restart s=worker
	$(COMPOSE) restart $(s)

build: init ## Rebuild images
	$(COMPOSE) build

ps: ## Service status
	$(COMPOSE) ps

logs: ## Follow logs; one service with s=api
	$(COMPOSE) logs -f --tail=100 $(s)

urls: ## Show local URLs
	@echo ""
	@echo "  Accountant console    http://localhost:3000"
	@echo "  API (Swagger)         http://localhost:8000/docs"
	@echo "  Flower                http://localhost:5555"
	@echo "  RabbitMQ              http://localhost:15672  (wallbit / wallbit)"
	@echo "  Prometheus            http://localhost:9090"
	@echo "  Grafana               http://localhost:3001"
	@echo ""

health: ## Check the API responds
	@curl -fsS http://localhost:8000/health && echo

clean: ## Stop everything and DELETE volumes (DB, queues, metrics)
	$(COMPOSE) down -v --remove-orphans

# ---------- database ----------
migrate: ## Apply pending migrations
	$(API) alembic upgrade head

migration: ## Create a migration: make migration m="add clients"
	@test -n "$(m)" || (echo 'Missing message: make migration m="..."' && exit 1)
	$(API) alembic revision --autogenerate -m "$(m)"

seed: ## Load demo data (2 clients)
	$(API) python -m seeds.run

seed-volume: ## Load N active clients for load tests: make seed-volume n=2000
	$(API) python -m seeds.volume --clients $(or $(n),2000)

shell: ## Shell inside the API container
	$(API) bash

psql: ## Postgres console
	$(COMPOSE) exec postgres sh -c 'psql -U $$POSTGRES_USER -d $$POSTGRES_DB'

rabbit: ## RabbitMQ queues with messages and consumers
	$(COMPOSE) exec rabbitmq rabbitmqctl list_queues name messages consumers

# ---------- quality ----------
test: test-back test-web ## Run all tests

test-back: ## Backend tests
	$(API) pytest -q

test-web: ## Web console tests
	$(WEB) npm test

e2e: ## Demo e2e in a real browser (Playwright, against `make up`; resets demo data)
	cd web && npm run e2e

lint: ## Backend lint (web ESLint comes with the console)
	$(API) ruff check .
	$(API) ruff format --check .

fmt: ## Format the backend
	$(API) ruff check --fix .
	$(API) ruff format .

typecheck: ## Type check (mypy + tsc)
	$(API) mypy app
	$(WEB) npm run typecheck

api-client: ## Regenerate the TS client from the API OpenAPI
	$(WEB) npx openapi-typescript http://api:8000/api/v1/openapi.json -o src/lib/api/schema.d.ts

load: ## k6 load test: make load scenario=month_close_burst (then accountant_inbox)
	docker run --rm -i --network cierre_default -v $(CURDIR)/tests/load:/scripts grafana/k6:0.54.0 run /scripts/$(or $(scenario),month_close_burst).js
