# Estrategia de testing

## Pirámide

| Nivel | Herramienta | Qué cubre |
|---|---|---|
| Unit (backend) | `pytest` + `hypothesis` | Motor fiscal, reglas de clasificación, alertas, máquina de estados. Property-based: ej. "la suma de ingresos clasificados nunca supera lo cobrado", "recalcular con los mismos inputs da el mismo snapshot" |
| Golden cases | `pytest` + fixtures YAML | Casos validados por el contador (input → resultado esperado). Si cambia el cálculo, falla y exige revisión |
| Integration | `pytest` + Postgres/RabbitMQ (compose de test) | Repositorios, transacciones, tasks Celery end-to-end, aprobación en lote |
| Contract | `schemathesis` | La API cumple su OpenAPI (fuzzing de endpoints) |
| Unit (web) | `Vitest` + Testing Library | Componentes y hooks de la consola |
| E2E | `Playwright` | Flujo del contador: bandeja → revisar → aprobar lote → ver notificado |
| Carga | `k6` | Ver abajo |

## k6 — escenarios

| Escenario | Simula | Umbrales (thresholds) |
|---|---|---|
| `month_close_burst` | Día 1: genera 2.000 clientes con la factory de volumen (no el seed de demo), dispara el cierre y mide hasta que todos salen de `PENDING/COMPUTED` | 100% procesado < 10 min con 2 workers; 0 tasks en DLQ |
| `accountant_inbox` | 5 contadores navegando bandeja y detalle | p95 < 300 ms, errores < 1% |
| `batch_approve` | Aprobar 500 cierres READY en una operación | < 5 s, idempotente ante reintento |
| `users_confirm_invoices` | 2.000 usuarios confirmando facturas en 1 h (ráfaga de recálculos) | p95 API < 500 ms, cola `recompute` drenada < 1 min |

Resultados exportados a Prometheus → dashboard de Grafana "Load tests".

## Dónde corre cada cosa

| Instancia | Qué corre | Objetivo |
|---|---|---|
| **pre-commit** | `ruff`, `ruff format`, `mypy` (archivos cambiados), `eslint`, `prettier`, `gitleaks`, `check-yaml/json`, unit del `tax_engine` | Feedback < 10 s |
| **commit-msg** | `commitlint` | Conventional Commits |
| **pre-push** | Unit completos backend + web | No pushear rojo |
| **CI — PR** (GitHub Actions) | Lint + types, unit con cobertura, integration (services: postgres, rabbitmq), drift del cliente OpenAPI, build de imágenes, e2e Playwright sobre compose | Gate de merge |
| **CI — dev (push)** | Todo lo anterior + `schemathesis` + k6 smoke (1 VU, 1 min) | `dev` siempre verde |
| **CI — nightly / manual** | k6 completo (`month_close_burst`, etc.) sobre compose | Detectar regresiones de performance |
| **CI — release/\*** | Suite completa + golden cases + reporte de cambios en cálculo fiscal para firma del contador | Validación regulatoria |

## Cobertura

- `tax_engine`, `classification`, `alerts`, `closing`: ≥ 95%.
- Global backend: ≥ 80%. Web: sin umbral duro, foco en flujos críticos.
