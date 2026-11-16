# Code Conventions

## Generales

- **Código, identificadores, commits y nombres de ramas en inglés.** UI, mensajes al usuario y docs en español (rioplatense, voseo).
- Nada de secretos en el repo: `.env.example` versionado, `.env` ignorado; `gitleaks` en pre-commit.
- **Dinero**: nunca `float`. Python `Decimal`, DB `NUMERIC(18,2)` (montos) y `NUMERIC(18,6)` (tipos de cambio), TS `string` en el wire y formateo en el borde. Toda cifra lleva su moneda (`amount` + `currency`).
- **Fechas**: timestamps en UTC (`timestamptz`), conversión a `America/Argentina/Buenos_Aires` solo en presentación. Períodos como `YYYY-MM`.
- **IDs**: UUID.
- Ningún dato de usuario sale del sistema: prohibido llamar servicios externos con datos de clientes.

## Python (backend)

- Python 3.12, gestor `uv`.
- `ruff` (lint + format, línea 100), `mypy --strict`.
- Capas por módulo: `router` (HTTP, sin lógica) → `service` (casos de uso, transacciones) → `repository` (SQLAlchemy). `schemas.py` Pydantic para I/O, `models.py` para ORM; **nunca** devolver modelos ORM desde un router.
- `tax_engine`, reglas de `classification` y `alerts`: **funciones puras**, sin I/O, sin `datetime.now()` (se inyecta la fecha), entradas/salidas como dataclasses o modelos Pydantic inmutables (`frozen=True`).
- Todo resultado fiscal devuelve una **traza** explicable (`list[TraceStep]`).
- Naming: `snake_case` funciones/variables, `PascalCase` clases, `UPPER_SNAKE` constantes. Enums `StrEnum`.
- Errores de dominio como excepciones propias (`DomainError` y subclases); se mapean a HTTP en un único handler.
- Celery tasks: nombre `<module>.<verb_noun>`, idempotentes, argumentos serializables simples (ids, no objetos), `acks_late=True`.
- Logging estructurado JSON (`structlog`) con `request_id` / `task_id`; **nunca** loguear montos junto a CUIT o nombre.

## API

- REST bajo `/api/v1`, recursos en plural y kebab-case: `/period-closes/{id}/approve`.
- Acciones de dominio como sub-recursos POST (`/approve`, `/reopen`, `/batch-approve`).
- Errores en formato **RFC 7807** (`application/problem+json`) con `code` estable.
- Paginación por cursor (`?cursor=&limit=`), filtros explícitos (`?status=READY&period=2026-10`).
- Operaciones masivas aceptan `Idempotency-Key`.
- El OpenAPI es el contrato: el cliente TS se regenera (`make api-client`) y CI falla si hay drift.

## Base de datos

- Tablas y columnas `snake_case`, tablas en plural.
- Toda tabla: `id`, `created_at`, `updated_at`. `audit_events` es append-only (sin UPDATE/DELETE, reforzado con permisos).
- Migraciones Alembic, una por PR, nombradas `YYYYMMDD_HHMM_<slug>`. Sin cambios destructivos sin migración en dos pasos.
- Snapshots aprobados son inmutables: correcciones = reapertura + nuevo snapshot.

## TypeScript (web y mobile)

- `strict: true`, `noUncheckedIndexedAccess: true`. Prohibido `any` (usar `unknown`).
- ESLint + Prettier. Imports absolutos con alias `@/`.
- Componentes `PascalCase.tsx`, hooks `useXxx.ts`, utilidades `camelCase.ts`.
- Datos remotos solo vía TanStack Query + cliente generado; nada de `fetch` suelto en componentes.
- Estado de servidor ≠ estado de UI: no duplicar en stores.
- Formateo de dinero/fechas centralizado (`formatMoney`, `formatPeriod`) con `Intl`, locale `es-AR`.
- Next.js: Server Components por defecto; `"use client"` solo donde hay interacción.

## Tests

- Python: `test_<unidad>.py`, funciones `test_<comportamiento>_when_<condición>`. Fixtures en `conftest.py`, factories con `factory_boy`.
- TS: `*.test.ts(x)` junto al archivo; e2e en `tests/e2e/*.spec.ts`.
- Cada bug fix incluye el test que lo reproduce.
- Detalle de la estrategia en [TESTING.md](TESTING.md).

## Docs

- Decisiones relevantes como ADR en `docs/adr/NNNN-<slug>.md` (contexto, decisión, consecuencias).
