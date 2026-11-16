# Testing

Este documento distingue **lo que está implementado** de **lo que queda como plan**. No describe nada como hecho si no corre hoy.

## Implementado

| Nivel | Herramienta | Qué cubre | Cómo correrlo |
|---|---|---|---|
| Unit del dominio | `pytest` | Clasificador por capas, motor fiscal y alertas o estado, como funciones puras sin base de datos (33 tests) | `make test-back` |
| Golden cases | `pytest` | Casos fiscales con resultado esperado: los clientes de la demo (84% y 58% del tope), supera categoría, supera régimen, cuota de bienes, vencimiento en enero. Si cambia el cálculo, fallan y exigen revisión | `make test-back` |
| Integración | `pytest` + Postgres real (base `wallbit_test`) | Lo que se verifica: <ul><li>esquema: auditoría append-only y particionada, snapshots inmutables;</li><li>flujo del usuario por la API: adhesión, ARCA, avisos, facturar;</li><li>cierre del día 1 y del día 5, y que recalcular sin cambios no cambia el resultado;</li><li>acciones del contador: resolver o deshacer, clasificar, conversación, aprobar;</li><li>lote idempotente, paginación de la bandeja.</li></ul>34 tests. Cada uno corre en una transacción que se descarta al final | `make test-back` |
| E2E | Playwright (Chromium) | La demo completa en un navegador real, de la adhesión hasta el usuario notificado. Falla ante cualquier error en la consola del navegador | `make e2e` |
| Carga | k6 | Ver abajo | `make load` |

## k6: escenarios

Se corren contra el compose levantado, con el **seed de volumen**, no con el de la demo: `make seed-volume n=2000` genera 2.000 clientes activos con casos borde (~70% sin problemas, ~15% con un cobro sin factura, ~10% con una transferencia de una persona desconocida, ~5% cerca del tope).

| Escenario | Qué simula | Umbrales | Resultado medido (16/11, laptop, 1 worker con 2 procesos) |
|---|---|---|---|
| `month_close_burst` | El día 1: dispara el cierre y espera a que los 2.000 estén calculados | 100% en < 10 min, cola de mensajes muertos vacía | **15,2 s**. Resultado: 1.522 listos, 281 en revisión, 197 esperando al usuario. Cola de muertos: 0 |
| `accountant_inbox` | 5 contadores durante 1 minuto: bandeja, detalle y vista previa del mensaje | p95 < 300 ms por pantalla, errores < 1% | p95: bandeja **115 ms**, detalle **31 ms**, vista previa **14 ms**. 0 errores |

```bash
make seed-volume n=2000
make load scenario=month_close_burst
make load scenario=accountant_inbox
make seed            # volver a los datos de la demo
```

La primera versión de la bandeja devolvía los 2.000 cierres y daba p95 de 533 ms. k6 lo detectó, y la bandeja se paginó en el backend, con orden por prioridad en SQL y totales con consultas agregadas. Mientras corre la carga, se puede seguir en Grafana, en el dashboard *Plataforma*.

## Dónde corre cada cosa

| Instancia | Qué corre | Estado |
|---|---|---|
| **pre-commit** | espacios y fin de archivo, YAML/JSON/TOML, conflictos, archivos grandes, `gitleaks`, `ruff`, `ruff format`, `mypy`, `tsc` | Implementado |
| **commit-msg** | `commitlint` (types y scopes de GITFLOW) | Implementado |
| **pre-push** | `pytest` del backend | Implementado |
| **CI** (`.github/workflows/ci.yml`) | `backend`: ruff, mypy y pytest con Postgres como servicio · `web`: tsc y `next build` · `e2e`: compose completo, seed y Playwright | Escrito y validado localmente paso por paso. Se ejecuta cuando el repo tenga remoto en GitHub |

## Pendiente (plan, no implementado)

- **Tests de la web con Vitest:** la UI hoy se cubre con el e2e.
- **Contrato con `schemathesis`** sobre el OpenAPI.
- **Property-based con `hypothesis`**, por ejemplo: "lo clasificado como ingreso nunca supera lo cobrado".
- **k6 `batch_approve`** (aprobar 500 cierres listos en menos de 5 s) y la ráfaga de recálculos por respuestas de usuarios.
- **Exportar los resultados de k6 a Prometheus**, con un dashboard "Load tests".
- **Más en la CI:** umbral de cobertura (dominio ≥ 95%), chequear que el cliente del OpenAPI no quedó desactualizado, k6 corto en cada push a `dev` y k6 completo nightly.
