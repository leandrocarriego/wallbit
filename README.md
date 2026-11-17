# Cierre · Servicio contable Wallbit

Prototipo de la herramienta de **cierre de mes** para el contador matriculado de Wallbit: freelancers argentinos en monotributo que cobran del exterior.

**La herramienta calcula todo y el contador aprueba excepciones.** Nada impositivo le llega al usuario sin una aprobación registrada del contador, y ningún dato de los usuarios sale del sistema.

Las decisiones están resumidas en [NOTA_DE_DECISIONES.md](NOTA_DE_DECISIONES.md).

## Levantarlo

Requisito: Docker con Docker Compose.

```bash
make up      # levanta todo: Postgres, RabbitMQ, API, workers, web, Flower, Prometheus, Grafana
make seed    # carga la demo: 2 usuarios sin adherir y sus movimientos de octubre 2026
```

La primera vez tarda unos minutos porque construye las imágenes. Las migraciones se aplican solas al arrancar la API.

| Qué | Dónde |
|---|---|
| Inicio de la demo | http://localhost:3000 |
| Consola del contador | http://localhost:3000/consola |
| App del usuario (simulador) | http://localhost:3000/app |
| API (Swagger) | http://localhost:8000/docs |
| Flower (tareas de Celery) | http://localhost:5555 |
| RabbitMQ | http://localhost:15672 (wallbit / wallbit) |
| Grafana: dashboards *Cierre del mes*, *Productividad del contador* y *Plataforma* | http://localhost:3001 |
| Prometheus | http://localhost:9090 |

`make seed` deja los datos como al principio de la demo; se puede correr las veces que haga falta. `make down` apaga todo y `make clean` además borra los datos.

## Guion de la demo (unos 5 minutos)

Abrí la **consola** y la **app** en dos pestañas. Todo está en fecha simulada: arranca el 31/10/2026.

1. **Adhesión (app).** Elegí a Mateo → *Conocer más* → *Quiero mi contador* → aceptá el consentimiento → *Vincular con ARCA*. Repetí con **Martina**.
   - Al vincular, se importan sus facturas y **se clasifican sus movimientos en el momento**.
   - A Martina le aparecen dos avisos: *Facturar este cobro* (Acme le pagó USD 1.200 sin factura) y *¿Quién es J. Pérez?*. **No los respondas todavía.**
2. **Día 1 (consola).** *Simular día 1* hace lo mismo que la tarea programada del día 1. Celery calcula los cierres: Martina queda **en revisión** y Mateo **listo**, con el plan del día y el tiempo estimado.
3. **Día 5.** *Simular día 5*: Martina no respondió, así que J. Pérez pasa al contador.
4. **Revisión guiada.** Abrí a Martina (atajos J/K para moverte, A para aprobar).
   - En el cobro sin facturar, *Escribirle a Martina* → *Enviar*.
5. **App de Martina.** Aparece *Tu contador te escribió*. *Facturar este cobro* → *Emitir factura* (ARCA simulado) y respondé.
6. **Consola.**
   - La alerta del cobro desaparece sola: la factura llegó de ARCA y quedó vinculada al cobro.
   - En J. Pérez, *Aplicar sugerencia* (se puede deshacer).
   - Aceptá la declaración y *Aprobar*: se congela un snapshot inmutable y sale el aviso.
7. **Lote.** *Aprobar en lote* → declaración → aprobar a Mateo.
8. **App.** Los dos ven *Revisado por tu contador*, con la cuota, el vencimiento y el mensaje aprobado.

En la pestaña *Historial* del detalle, o en la tabla `audit_events` (`make psql`), queda cada paso registrado con quién lo hizo. En Grafana (*Cierre del mes*) se ve el avance del período y en *Plataforma*, las colas y los workers durante el día 1.

## Cómo está hecho

- **Backend:** FastAPI + SQLAlchemy + Alembic sobre PostgreSQL. **Celery con RabbitMQ** tiene tres colas: el cálculo masivo del día 1, los recálculos interactivos y las notificaciones. Hay una cola de mensajes muertos y tareas programadas para el día 1, el día 5, un barrido cada 5 minutos y el recordatorio del día 17.
- **Dominio como funciones puras, con traza:**
  - **clasificador por capas**: tipo de movimiento → reglas globales → factura de ARCA → historial con esa contraparte → declaración del usuario → sugerencia;
  - **motor fiscal del monotributo**, con parámetros versionados en la base de datos;
  - **alertas**: bloqueantes, en espera del usuario o informativas.
- **Garantías:**
  - Postgres es la fuente de verdad y los mensajes de la cola solo llevan ids;
  - las tareas se encolan después del commit;
  - recalcular sin cambios no cambia el resultado (hash de los datos de entrada y bloqueo de fila);
  - la aprobación en lote no se duplica si se reintenta (`Idempotency-Key`);
  - la auditoría es append-only y está particionada por mes;
  - los snapshots aprobados son inmutables, con triggers en la base de datos.
- **ARCA** está detrás de dos puertos, uno para leer facturas y otro para emitirlas. En el prototipo es un ARCA simulado en la base de datos; la propuesta es AfipSDK ([ARCHITECTURE §10](docs/ARCHITECTURE.md)).
- **Web:** Next.js + Tailwind con el design system propio. Los tipos se generan desde el OpenAPI. La app del usuario se simula dentro de la misma web.

Documentación en [`docs/`](docs/):
- [arquitectura](docs/ARCHITECTURE.md) y [flujo](docs/FLOW.md);
- [convenciones](docs/CONVENTIONS.md), [testing](docs/TESTING.md) y [git flow](docs/GITFLOW.md);
- diseño: [design system](docs/DESIGN_SYSTEM.md), [wireframes](docs/wireframes.html) y alta fidelidad en [`docs/hifi/`](docs/hifi/).

## Tests

```bash
make test-back   # 72 tests: dominio puro con golden cases + integración contra Postgres real
make e2e         # la demo completa en un navegador real (Playwright); reinicia los datos
make lint        # ruff
make typecheck   # mypy estricto + tsc
```

**Carga (k6), con 2.000 clientes.** `make load-all` corre el mes entero en orden:

```bash
make seed-volume n=2000                  # 2.000 clientes activos con casos borde
make load scenario=user_activity rate=50 # cobros llegando y usuarios respondiendo: p95 23 ms
make load scenario=month_close_burst     # día 1: 2.000 cierres en ~20 s (objetivo < 10 min)
make load scenario=late_answers          # 478 respuestas a la vez: todo recalculado en 8 s
make load scenario=day_5_expiry          # día 5: 1.956 cierres recalculados en 17 s
make load scenario=accountant_workday    # 5 contadores + lote de 1.522 cierres en 4 s
make load scenario=accountant_inbox      # bandeja p95 115 ms (objetivo < 300 ms)
make seed                                # volver a la demo
```

Límites medidos en la laptop:
- **Día 1:** ~25–30 mil clientes en menos de 10 minutos.
- **Actividad de usuarios:** ~55 eventos/s por proceso de API.
- **Trabajo del contador:** se mide en el dashboard *Productividad del contador*.

Detalle de qué está implementado y qué queda como plan: [docs/TESTING.md](docs/TESTING.md). La CI (`.github/workflows/ci.yml`) corre lint, tipos, tests y e2e.

`make e2e` necesita Node en la máquina. La primera vez: `cd web && npm ci && npx playwright install chromium`.

## Supuestos del prototipo

- **Datos:** son ficticios, igual que las cifras fiscales (topes y cuotas). Las cifras se cargan como parámetros versionados y no están en el código.
- **Alcance de la v1:** solo monotributistas que facturan servicios al exterior con Factura E.
- **Facturas e ingesta:** ARCA está simulado, así que no se conecta a ningún servicio externo. Los movimientos de Wallbit salen del seed.
- **Sin login:** un selector "¿Quién sos?" reemplaza la autenticación. El header `X-Actor` registra igual en la auditoría quién hizo cada acción.
- **Fechas:** un reloj de demo simula el calendario del cierre.
- **Desarrollo:** el worker de Celery no se recarga solo cuando cambia el código. Después de tocar el backend: `make restart s=worker`.
