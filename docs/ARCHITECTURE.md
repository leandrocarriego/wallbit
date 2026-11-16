# Arquitectura — Servicio Contable Wallbit

> Herramienta de cierre de mes para el contador matriculado de Wallbit.
> Principio rector: **la herramienta calcula todo, el contador aprueba excepciones.**
> Nada impositivo llega al usuario sin una aprobación registrada del contador.

## 1. Stack

| Capa | Tecnología | Rol |
|---|---|---|
| API | **FastAPI** (Python 3.12, `uv`, Pydantic v2, SQLAlchemy 2, Alembic) | API REST `/api/v1`, OpenAPI como contrato |
| Workers | **Celery** sobre **RabbitMQ** (broker) + **Celery Beat** | Cierre de mes masivo, recálculos, notificaciones |
| Monitor de colas | **Flower** | Estado de tasks/workers |
| Base de datos | **PostgreSQL 16** | Fuente de verdad (Celery sin result backend: el avance se lee de la DB) |
| Consola del contador | **Next.js** (App Router, TS strict, Tailwind + shadcn/ui, TanStack Query) | Bandeja de cierre, revisión, aprobación en lote |
| App del usuario (secundaria) | Páginas dentro de la web (prototipo); Expo a futuro | Simulador de la app de Wallbit: elegir qué cliente "soy", adherir (consentimiento + **vincular ARCA**), responder qué es cada contraparte, responder al contador con "Facturar este cobro" y ver mi cierre |
| Cliente API | `openapi-typescript` generado desde el OpenAPI de FastAPI | Tipos de la web generados desde la API, sin drift |
| Observabilidad | **Prometheus** + **Grafana** (+ exporters de Postgres, RabbitMQ, Celery) | Métricas técnicas y de negocio |
| Orquestación local | **Docker Compose** + **Makefile** | `make up` levanta todo |
| Calidad | pre-commit, pytest, Vitest, Playwright, Jest, k6, GitHub Actions | Ver [TESTING.md](TESTING.md) |

**Restricción de datos:** ningún servicio llama a APIs externas con datos de usuarios. La clasificación es por reglas deterministas (no LLM externo). Las notificaciones del prototipo son in-app (sin push); si en producción se usara push, el payload sería genérico ("Tenés novedades de tu cierre") y el detalle se lee dentro de la app.

## 2. Estructura del repo (monorepo)

```
.
├── backend/                  # FastAPI + Celery (un paquete, dos entrypoints)
│   ├── app/
│   │   ├── main.py           # FastAPI app
│   │   ├── worker.py         # Celery app + beat schedule
│   │   ├── core/             # config, db, auth, logging, metrics
│   │   └── modules/
│   │       ├── clients/          # perfil fiscal del cliente
│   │       ├── enrollment/       # adhesión, vincular ARCA, respuestas del usuario
│   │       ├── arca/             # puertos a ARCA (mock en el prototipo, AfipSDK a futuro)
│   │       ├── prompts/          # avisos y preguntas al usuario durante el mes
│   │       ├── demo/             # reloj de demo (solo prototipo)
│   │       ├── ingestion/        # movimientos Wallbit (read-only)
│   │       ├── invoices/         # facturas importadas de ARCA
│   │       ├── classification/   # reglas + correcciones del contador
│   │       ├── tax_engine/       # motor fiscal PURO y versionado
│   │       ├── alerts/           # reglas de riesgo
│   │       ├── closing/          # máquina de estados del cierre
│   │       ├── review/           # aprobación individual / en lote
│   │       ├── notifications/    # plantillas + envío
│   │       └── audit/            # log append-only
│   ├── migrations/           # Alembic
│   ├── seeds/                # generador de datos ficticios
│   └── tests/{unit,integration,contract}
├── web/                      # Next.js — consola del contador
├── packages/api-client/      # tipos TS generados desde OpenAPI
├── infra/
│   ├── prometheus/prometheus.yml
│   └── grafana/{provisioning,dashboards}
├── tests/
│   ├── e2e/                  # Playwright (web)
│   └── load/                 # k6
├── docs/
├── .github/workflows/
├── .pre-commit-config.yaml
├── docker-compose.yml
└── Makefile
```

Cada módulo de backend sigue: `router.py` → `service.py` → `repository.py`, con `models.py` (SQLAlchemy) y `schemas.py` (Pydantic). `tax_engine/` y las reglas de `classification/` y `alerts/` **no importan nada de FastAPI ni de la DB**: son funciones puras testeables.

## 3. Servicios (docker compose)

| Servicio | Puerto | Notas |
|---|---|---|
| `postgres` | 5432 | |
| `rabbitmq` | 5672 / 15672 (UI) | plugin prometheus en 15692 |
| `api` | 8000 | `/docs` (Swagger), `/metrics` |
| `worker` | — | `celery -A app.worker worker`, escalable con `--scale worker=N` |
| `beat` | — | dispara el cierre el día 1 de cada mes |
| `flower` | 5555 | |
| `web` | 3000 | consola del contador |
| `prometheus` | 9090 | |
| `grafana` | 3001 | dashboards provisionados |
| `postgres-exporter`, `celery-exporter` | — | |

## 4. Componentes de dominio

```
Durante el mes (continuo):
Movimiento nuevo ─▶ Clasificación ─▶ ¿cobro sin factura? ─▶ aviso al usuario "Facturar este cobro"
Factura de ARCA ──┘                └▶ ¿desconocido?       ─▶ pregunta "¿Quién es…?"

Día 1 (consolidación):
Clasificaciones del mes ─▶ Motor fiscal ─▶ Alertas ─▶ Cierre (estado) ─▶ Revisión ─▶ Notificación
                                                                  Audit log ◀───────┘ (todo evento)
```

**Clasificación continua, cierre mensual** (decisión 20): cada movimiento se clasifica cuando llega (y al vincular ARCA, los del mes en curso). Así el usuario factura o aclara en el momento, y lo que el día 1 le llega al contador es solo lo que quedó sin resolver. Una clasificación se recalcula si llega una factura, una respuesta del usuario o una regla global nueva; el cierre del día 1 toma el estado final.

1. **Ingesta**: adaptador read-only sobre movimientos de Wallbit (en el prototipo, el seed). Cobros, transferencias, conversiones a stablecoin, gastos con tarjeta, con tipo de cambio de cada operación.
2. **Clasificación**: función pura `classify(movement, ctx) -> Classification + Trace`, capas en orden (gana el primer match). **No hay reglas por cliente**: lo que solo sabe el usuario lo declara el usuario; el contador valida por excepción.
   1. **Estructural** (tipo de movimiento de Wallbit: conversión, tarjeta, interés, transferencia interna).
   2. **Reglas globales** (pocas, las mantiene el contador): plataformas conocidas (Deel, Upwork…), nombre del ordenante = titular (Payoneer/PayPal/Wise → `platform_withdrawal`; otro banco → `own_transfer`).
   3. **Match con factura de ARCA** (contraparte, monto con tolerancia por comisiones, ventana de fechas; o vínculo explícito si se emitió con "Facturar este cobro"). Vincula cobro ↔ factura. Si no hay factura pero el usuario **ya le facturó antes a esa contraparte en ARCA**, es cobro por trabajo sin factura (historial ARCA) → aviso "Facturar este cobro".
   4. **Declaración del usuario por contraparte** (`counterparty_declarations`: `client_id` + contraparte normalizada → categoría). Se responde una vez y aplica a los movimientos futuros de esa contraparte.
   5. **`Suggester`** → solo *sugiere*, nunca clasifica: `Suggester.suggest(movement, ctx) -> Suggestion | None` (categoría, score, motivo). v1 = heurística determinista (recurrencia, memo, monto estable). Futuro: modelo ML local (scikit-learn/LightGBM) entrenado con declaraciones del usuario + validaciones del contador, versionado, con umbral mínimo y versión en la traza/snapshot. Pre-completa la pregunta al usuario y la sugerencia al contador. Clasificación automática solo en alta confianza y con precisión ya medida.
   6. **Pregunta al usuario** (`unclassified`, una por contraparte, en lenguaje simple: *Trabajo · Transferencia mía · Familia o regalo · Otro*). Si no responde al día 5, o responde "Otro" → pasa al contador (alerta bloqueante "sin clasificar"). El contador resuelve en "Resolver por alerta"; puede crear regla global.

   **Validación por excepción**: una declaración del usuario como *no facturable* genera alerta para el contador si hay señales de riesgo (monto alto, recurrente, memo tipo "invoice", patrón de cobro por servicios). El resto entra en la aprobación en lote del cierre. Mitiga el incentivo a declarar "regalo" para no facturar.

   Categorías: `service_income` (facturable) · `platform_withdrawal` (retiro de Payoneer/PayPal/Wise propio: facturable, el origen real son clientes) · `own_transfer` · `conversion` · `refund_reversal` · `investment_income` · `personal_transfer` · `card_expense` · `unclassified`. Cada clasificación guarda `source` (`structural | global_rule | invoice_match | user_declared | accountant | model`), `rule_id`/`declaration_id` y traza. Contrapartes normalizadas ("ACME CORP" = "Acme Corp."). Cada respuesta del usuario y cada validación del contador queda como etiqueta para el modelo futuro.
3. **Motor fiscal** (v1: monotributo): `compute_close(profile, movements, invoices, params) -> CloseResult + Trace`. Parámetros (categorías, topes, cuotas, vencimientos) versionados con vigencia, cargados por el contador.
4. **Alertas**: declaración "no facturable" con señales de riesgo, cobrado sin facturar, facturado sin cobro, movimientos sin clasificar, >80% del tope, supera categoría, supera máximo del régimen, preguntas sin responder. Severidad `blocking | waiting | info`.
5. **Cierre**: máquina de estados por cliente y período (ver abajo).
6. **Revisión**: aprobación individual o en lote; al aprobar se congela un **snapshot inmutable** (inputs, resultado, versión de motor y parámetros, aprobador, timestamp).
7. **Notificaciones**: solo desde snapshot aprobado, con plantillas validadas por el contador.
8. **Audit**: tabla append-only con actor, acción, entidad, antes/después.

### Máquina de estados del cierre

```
PENDING_DATA ──(usuario responde)──▶ COMPUTED
COMPUTED ──(sin bloqueantes)──▶ READY
COMPUTED ──(con bloqueantes)──▶ IN_REVIEW ──(contador resuelve)──▶ READY
READY ──(aprobación individual/lote)──▶ APPROVED ──▶ NOTIFIED
(dato nuevo en cualquier estado previo a APPROVED) ──▶ recálculo idempotente
APPROVED/NOTIFIED ──(reabrir, con motivo)──▶ IN_REVIEW
```

## 5. Mensajería (RabbitMQ / Celery)

| Cola | Tasks | Por qué separada |
|---|---|---|
| `closing` | `start_period_close(period)` → fan-out `compute_client_close(client_id, period)` | Ráfaga del día 1; se escala horizontalmente |
| `recompute` | `classify_movement` (movimiento nuevo), `reclassify_client_period` (factura de ARCA, respuesta, regla nueva), `recompute_client_close` (corrección del contador) | Interactivo: no debe esperar detrás de la ráfaga |
| `notifications` | `send_close_notification`, `send_due_reminder`, `send_user_prompt` ("Facturar este cobro", "¿Quién es?") | Aislar fallos de envío |

**Principio: Postgres es la fuente de verdad; RabbitMQ solo transporta disparadores.** Los mensajes llevan ids (`client_id`, `period`, `notification_id`), nunca datos. El worker siempre lee el estado actual de la DB. Si un mensaje se pierde o se duplica, no se pierde ni se corrompe nada.

- Tasks **idempotentes** (clave `client_id + period + inputs_hash`), `acks_late=True`, `prefetch=1`, reintentos con backoff, dead-letter queue (con alerta en Grafana si recibe algo).
- **Encolar después del commit + flag `dirty` + barrido**: la API guarda el cambio, marca el cierre `dirty` y escribe auditoría en una transacción; recién después del commit encola. Un barrido periódico re-encola lo `dirty` y las notificaciones pendientes. Evita perder recálculos (caída entre commit y encolado) y leer datos viejos (encolar antes del commit). Es un outbox liviano; suficiente para la v1.
- **Sin carreras**: el recálculo toma `SELECT … FOR UPDATE` sobre la fila del cierre y descarta el resultado si el `inputs_hash` cambió mientras calculaba. Si el cierre está `APPROVED`/`NOTIFIED`, el recálculo no hace nada (solo se reabre con motivo).
- **Notificación exactamente una vez (en efecto)**: la fila `notification` se crea en la misma transacción que el snapshot, única por `snapshot_id`; el envío revisa su estado antes de mandar.
- **Auditoría en la misma transacción que el cambio**, nunca vía cola. Correlación: el `request_id` de la API viaja en los headers del mensaje; los eventos de workers guardan actor `system`, `task_id` y `request_id`. Opcional: cadena de hashes (`prev_hash`) en `audit_events` para detectar alteraciones.
- **Snapshot reproducible**: `inputs_hash` + versión del motor + versión de parámetros → se puede recalcular y verificar que da lo mismo.
- **Escala**: más workers en `closing`; el primer cuello es Postgres → pool de conexiones por proceso (SQLAlchemy) en el prototipo, PgBouncer en producción; índices por `(client_id, period)`. Aprobación en lote en transacciones de ~100 cierres. Sin result backend de Celery: el avance se lee de la DB.
- **Beat**: día 1 00:05 → `start_period_close`; día 6 00:00 (hora AR, vencido el día 5) → `expire_pending_questions` (`PENDING_DATA` → `IN_REVIEW`; preguntas de contraparte sin respuesta → contador); cada 5 min → `sweep_dirty_closes` y `sweep_pending_notifications`; día 17 → recordatorios de vencimiento.

## 5.1 Cuellos de botella (y cómo se mitigan)

| # | Cuello | Mitigación |
|---|---|---|
| 1 | **El contador** (producto): si 15% cae en revisión son ~300 casos/mes concentrados entre el día 5 y 7 | Resolver por alerta, reglas globales que crecen, respuestas del usuario antes del día 5. Medir: % auto-aprobable, minutos de revisión por cliente, cola de revisión mes a mes |
| 2 | **El usuario que no responde** (alimenta al 1) | Facturas precargadas, recordatorio día 3, una pregunta por contraparte. Medir tasa de respuesta antes del día 5 |
| 3 | **Tormenta de recálculos**: regla global nueva, nueva versión de parámetros, ediciones seguidas del mismo usuario | Dedupe con flag `dirty` (si ya está encolado no se re-encola); recálculos masivos en `closing`, no en `recompute`; la consola muestra "recalculando N cierres…" |
| 4 | **Acumulado 12 meses** | Se toma el facturado de los snapshots aprobados de meses anteriores; solo se calcula el mes actual (costo fijo) |
| 5 | **Beat es punto único de falla** | `start_period_close` idempotente + chequeo de catch-up al iniciar Beat y en cada barrido; alerta si el día 1 a la 01:00 hay 0 cierres creados |
| 6 | **Postgres a mediano plazo** | `audit_events` particionada por mes (declarative partitioning; PK incluye `created_at`); índices `(period, status)` y `(period, alert_type)`; lote en transacciones de ~100 |
| 7 | **Producción** (no en el prototipo) | Leer movimientos de Wallbit desde réplica/export; límites de tasa de push/email aislados en la cola `notifications` |

RabbitMQ no es cuello a esta escala.

## 6. Observabilidad

- **Técnicas**: latencia/errores de la API, profundidad de colas, throughput y fallos de tasks, conexiones Postgres.
- **Negocio** (dashboard "Cierre del mes"): clientes por estado, % auto-aprobables, alertas por tipo, tiempo medio de revisión por cliente, tiempo hasta 100% notificado.

## 7. Sin autenticación (decisión del prototipo)

- No hay login ni roles: simplifica el desarrollo y la demo.
- La consola web asume **un único contador** (`accountant-demo`).
- El simulador del usuario (dentro de la web) tiene un **selector de cliente** ("simular ser…") y opera sobre endpoints del cliente: `/api/v1/clients/{client_id}/...`.
- El audit log igual registra al actor: header opcional `X-Actor` (default `accountant-demo` en la consola, `client:<id>` en el simulador del usuario). Así la trazabilidad regulatoria se ve en la demo aunque no haya auth.
- En producción se usaría el SSO/identidad existente de Wallbit; queda fuera de alcance.

## 7.1 Prioridades de construcción

1. **Backend** (motor fiscal, clasificación, alertas, cierre, aprobación en lote, workers) — foco principal.
2. **Consola web del contador** — foco principal.
3. **Simulador del usuario (en la web)** — adhesión + ARCA, inicio con avisos, "¿Quién es?", "Facturar este cobro", mensajes y mi cierre. Expo queda para después del prototipo.

## 8. Supuestos

- v1 solo **monotributistas** que facturan servicios al exterior (Factura E).
- Las facturas se leen de **ARCA**, que el usuario vincula al adherir (obligatorio). En el prototipo, ARCA está simulado; en la propuesta, AfipSDK (§10).
- Lo cobrado fuera de Wallbit solo existe si el usuario lo declara.
- Tipo de cambio para facturas: el que declara el usuario al facturar (validado contra el de la operación en Wallbit).
- Montos en `Decimal` / `NUMERIC`; nunca `float`.

## 9. Decisiones de UX (acordadas sobre wireframes)

- **Alertas bloqueantes sin excepción**: no existe "aprobar con motivo". Un cierre con bloqueantes solo se aprueba después de resolverlas con una acción explícita que queda en el audit log.
- **Resolución por tipo de alerta, en masa**: pantalla "Resolver por alerta". "Sin clasificar" se agrupa por contraparte (clasificar una vez → todos sus movimientos, opcionalmente como regla global). Cada acción masiva genera un evento de auditoría por cliente afectado y dispara recálculo.
  - Endpoints: `GET /api/v1/period-closes/{period}/alerts/summary`, `POST /api/v1/alerts/bulk-resolve`, `POST /api/v1/classifications/bulk` (con `Idempotency-Key`).
  - Excepción: la exclusión del régimen de monotributo se revisa siempre cliente por cliente.
- **Plan del día + estimación** en la bandeja: 3 pasos en orden de impacto (① resolver por alerta → ② revisión guiada → ③ lote) con lo que queda en cada uno y "Te quedan ~X" calculado con los tiempos reales del contador del mes anterior (s por caso masivo, min por revisión individual) + escenario si los pendientes no responden al día 5.
- **Revisión guiada**: cola de `IN_REVIEW` ordenada por severidad ("12 de 41"); al aprobar pasa sola al siguiente. Atajos: `J`/`K`, `A` aprobar, `1` escribirle por la alerta, `2`/`Enter` aplicar sugerencia, `P` perfil, `?` ayuda.
- **Solo lo que requiere acción**: movimientos OK colapsados ("8 · 6 OK · 2 con alerta"); banner **"Qué cambió desde que lo viste"** (requiere guardar `last_viewed_at` por contador y cierre, y diferenciar contra el audit log).
- **Acción sugerida preseleccionada** (de la capa `Suggester`) y **Deshacer en vez de confirmar** (10 s) para acciones de resolución y masivas. La aprobación final mantiene la declaración del matriculado.
- **Lote con "variación fuerte"**: alerta informativa nueva si el facturado varía ±50% contra el promedio de 3 meses; la muestra del lote arranca por esos.
- **Conversación dentro de la alerta** (reemplaza el pedido unidireccional y el WhatsApp): hilo atado a una alerta (`alert_threads`, `alert_messages`), plantillas, el usuario responde desde la app y puede elegir una factura; la respuesta vuelve a la alerta con la acción "Vincular y resolver". Cada mensaje es evento de auditoría. Los mensajes son operativos (pedir datos); las cifras impositivas siguen saliendo solo del snapshot aprobado.
- **Perfil de cliente**: identidad y etiquetas de comportamiento, acumulado vs. tope con proyección, facturado mes a mes, promedio y estabilidad, cierres a tiempo, tiempo de respuesta, contrapartes conocidas con su origen, historial de cierres (snapshots), alertas recurrentes, notas internas y conversaciones.
- **UI de alta fidelidad**: shadcn/ui sobre un mini design system propio (tokens de color, tipografía, espaciado, radios, estados semánticos del cierre) definido antes de las pantallas finales.
- Wireframes navegables: [wireframes.html](wireframes.html).

## 10. Evolución: integración con ARCA vía AfipSDK (propuesta, fuera del prototipo)

Vincular ARCA es obligatorio para adherir (decisión 3). En el prototipo está simulado; la propuesta es integrarlo con **AfipSDK** para dos cosas:

1. **Leer los comprobantes emitidos** por el usuario y hacer el match cobro ↔ factura automáticamente. La alerta "cobro sin facturar" se basa en datos de ARCA y no hay paso manual de confirmar facturas.
2. **Emitir la Factura E desde la app**: un botón en el cobro detectado ("Facturar este cobro") que precarga cliente del exterior, monto y tipo de cambio. Cierra el ciclo en el mismo lugar donde el usuario ve el cobro.

**Diseño para que entre sin reescribir**: las facturas llegan por un puerto `InvoiceSource` con dos implementaciones, `MockArcaSource` (prototipo: comprobantes de un ARCA ficticio en la DB) y `AfipSdkSource` (propuesta). La emisión va por un puerto `InvoiceIssuer` (`MockArcaIssuer` / `AfipSdkIssuer`). La clasificación, el motor fiscal y las alertas no cambian. Orígenes de factura: `arca_imported` y `arca_issued`.

**En el prototipo**: simulado. Vincular ARCA importa los comprobantes del ARCA ficticio; "Facturar este cobro" crea el comprobante en ese ARCA y la factura con `source = arca_issued`, sin llamar a ningún servicio externo.

**A resolver antes de implementarlo**:
- **Datos fuera del sistema**: si AfipSDK opera como servicio en la nube, el CUIT y los comprobantes del usuario pasan por un tercero, en tensión con "los datos no salen de nuestros sistemas". Opciones: usar la librería en infraestructura propia, o acuerdo de procesamiento de datos con el proveedor. Decisión del área legal/regulatoria.
- **Autorización del usuario**: delegar en Wallbit (o en el contador) el acceso a los web services de facturación con clave fiscal; flujo de onboarding y revocación.
- **Certificados**: custodia de los certificados digitales y rotación.
- **Responsabilidad**: emitir una factura es un acto fiscal del usuario; el botón precarga y el usuario confirma, nunca se emite sin su acción explícita.
