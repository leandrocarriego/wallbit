# Wallbit · Challenge Product Engineer — Servicio contable

Prototipo de la herramienta de **cierre de mes** para el contador matriculado de Wallbit (freelancers argentinos que cobran del exterior, monotributo). Enunciado: `Wallbit - Challenge Product Engineer.pdf` (confidencial: no publicar ni compartir su contenido).

**Al empezar cada sesión: leé [docs/STATUS.md](docs/STATUS.md)** (estado, próximos pasos, decisiones). **Al terminar: actualizalo** (checklist, log de sesión, próximos pasos).

## Principio rector

La herramienta calcula todo, el contador aprueba excepciones. Nada impositivo llega al usuario sin aprobación registrada del contador. Los datos de usuarios no salen del sistema (sin LLMs/APIs externas con datos).

## Docs (fuente de verdad)

| Doc | Qué tiene |
|---|---|
| [docs/STATUS.md](docs/STATUS.md) | Estado, checklist, decisiones, próximos pasos, log de sesiones |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Stack, módulos, máquina de estados, colas, supuestos, decisiones UX |
| [docs/FLOW.md](docs/FLOW.md) | Diagramas Mermaid del flujo de cierre |
| [docs/CONVENTIONS.md](docs/CONVENTIONS.md) | Convenciones de código, API, DB |
| [docs/GITFLOW.md](docs/GITFLOW.md) | Ramas, Conventional Commits, PRs |
| [docs/TESTING.md](docs/TESTING.md) | Pirámide de tests, k6, dónde corre cada cosa |
| [docs/DESIGN_SYSTEM.md](docs/DESIGN_SYSTEM.md) | Tokens, reglas visuales, mapeo a shadcn/ui |

## Stack

FastAPI + Celery/RabbitMQ (+ Flower) + PostgreSQL · Next.js + shadcn/ui (consola del contador) · Expo (simulador de la app del usuario, prioridad baja) · Prometheus + Grafana · Docker Compose + Makefile · pytest, Vitest, Playwright, k6, pre-commit, GitHub Actions. **Sin autenticación** (decisión del prototipo).

## Reglas de trabajo

- Idioma: docs y UI en español rioplatense (voseo); código, commits y ramas en inglés.
- Prioridad: backend y consola web > app mobile.
- Dinero en `Decimal`/`NUMERIC`, nunca `float`. Fechas UTC, períodos `YYYY-MM`.
- Motor fiscal, reglas de clasificación y alertas = funciones puras con traza.
- Alertas bloqueantes bloquean la aprobación sin excepción.
- Cifras fiscales (topes, cuotas) son ficticias y versionadas en DB, nunca hardcodeadas.
- Entregable final: prototipo + nota de decisiones de máx. 10 líneas (ver STATUS.md).
