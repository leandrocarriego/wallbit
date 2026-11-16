# Cierre · comandos del día a día. `make` (o `make help`) lista todo.
SHELL := /bin/bash
COMPOSE := docker compose
API := $(COMPOSE) exec api
WEB := $(COMPOSE) exec web

.DEFAULT_GOAL := help
.PHONY: help init hooks precommit up up-mobile down restart build ps logs urls health clean \
        migrate migration seed shell psql rabbit \
        test test-back test-web lint fmt typecheck api-client load

help: ## Lista los comandos disponibles
	@awk 'BEGIN {FS = ":.*## "; printf "\nUso: make <comando>\n\n"} /^[a-zA-Z_-]+:.*## / {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)
	@echo

# ---------- entorno ----------
init: ## Crea .env desde .env.example si no existe
	@test -f .env || (cp .env.example .env && echo "Creado .env desde .env.example")

hooks: ## Instala los hooks de git (pre-commit, commit-msg, pre-push)
	uvx pre-commit install

precommit: ## Corre todos los hooks sobre todo el repo
	uvx pre-commit run --all-files

up: init ## Levanta todo (datos, API, workers, web, observabilidad)
	$(COMPOSE) up -d --build
	@$(MAKE) --no-print-directory urls

up-mobile: init ## Levanta todo + el simulador mobile (Expo web)
	@test -d mobile || (echo "Todavía no existe mobile/: es la prioridad 3 del plan." && exit 1)
	$(COMPOSE) --profile mobile up -d --build

down: ## Apaga los servicios (conserva los datos)
	$(COMPOSE) --profile mobile down

restart: ## Reinicia un servicio: make restart s=worker
	$(COMPOSE) restart $(s)

build: init ## Reconstruye las imágenes
	$(COMPOSE) build

ps: ## Estado de los servicios
	$(COMPOSE) ps

logs: ## Logs en vivo; un servicio con s=api
	$(COMPOSE) logs -f --tail=100 $(s)

urls: ## Muestra las URLs locales
	@echo ""
	@echo "  Consola del contador  http://localhost:3000"
	@echo "  API (Swagger)         http://localhost:8000/docs"
	@echo "  Flower                http://localhost:5555"
	@echo "  RabbitMQ              http://localhost:15672  (cierre / cierre)"
	@echo "  Prometheus            http://localhost:9090"
	@echo "  Grafana               http://localhost:3001"
	@echo ""

health: ## Verifica que la API responda
	@curl -fsS http://localhost:8000/health && echo

clean: ## Apaga todo y BORRA los volúmenes (DB, colas, métricas)
	$(COMPOSE) --profile mobile down -v --remove-orphans

# ---------- base de datos ----------
migrate: ## Aplica las migraciones pendientes
	$(API) alembic upgrade head

migration: ## Crea una migración: make migration m="add clients"
	@test -n "$(m)" || (echo 'Falta el mensaje: make migration m="..."' && exit 1)
	$(API) alembic revision --autogenerate -m "$(m)"

seed: ## Carga los datos ficticios (~480 clientes con casos borde)
	$(API) python -m seeds.run

shell: ## Shell dentro del contenedor de la API
	$(API) bash

psql: ## Consola de Postgres
	$(COMPOSE) exec postgres sh -c 'psql -U $$POSTGRES_USER -d $$POSTGRES_DB'

rabbit: ## Colas de RabbitMQ con mensajes y consumidores
	$(COMPOSE) exec rabbitmq rabbitmqctl list_queues name messages consumers

# ---------- calidad ----------
test: test-back test-web ## Corre todos los tests

test-back: ## Tests del backend
	$(API) pytest -q

test-web: ## Tests de la consola web
	$(WEB) npm test

lint: ## Lint del backend (ESLint de la web llega con la consola)
	$(API) ruff check .
	$(API) ruff format --check .

fmt: ## Formatea el backend
	$(API) ruff check --fix .
	$(API) ruff format .

typecheck: ## Chequeo de tipos (mypy + tsc)
	$(API) mypy app
	$(WEB) npm run typecheck

api-client: ## Regenera el cliente TS desde el OpenAPI de la API
	$(WEB) npx openapi-typescript http://api:8000/api/v1/openapi.json -o src/lib/api/schema.d.ts

load: ## Prueba de carga k6: make load scenario=accountant_inbox
	docker run --rm -i --network cierre_default -v $(CURDIR)/tests/load:/scripts grafana/k6:0.54.0 run /scripts/$(or $(scenario),accountant_inbox).js
