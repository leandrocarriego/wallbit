# Testing

Este documento distingue **lo que está implementado** de **lo que queda como plan**. No describe nada como hecho si no corre hoy.

## Implementado

| Nivel | Herramienta | Qué cubre | Cómo correrlo |
|---|---|---|---|
| Unit del dominio | `pytest` | Clasificador por capas, motor fiscal y alertas o estado, como funciones puras sin base de datos (33 tests) | `make test-back` |
| Golden cases | `pytest` | Casos fiscales con resultado esperado: los clientes de la demo (84% y 58% del tope), supera categoría, supera régimen, cuota de bienes, vencimiento en enero. Si cambia el cálculo, fallan y exigen revisión | `make test-back` |
| Integración | `pytest` + Postgres real (base `wallbit_test`) | Lo que se verifica: <ul><li>esquema: auditoría append-only y particionada, snapshots inmutables;</li><li>flujo del usuario por la API: adhesión, ARCA, avisos, facturar;</li><li>cierre del día 1 y del día 5, y que recalcular sin cambios no cambia el resultado;</li><li>acciones del contador: resolver o deshacer, clasificar, conversación, aprobar;</li><li>lote idempotente, paginación de la bandeja;</li><li>ingesta de movimientos: clasificación al llegar e idempotencia;</li><li>productividad: apertura registrada y tiempo de revisión.</li></ul>39 tests. Cada uno corre en una transacción que se descarta al final | `make test-back` |
| E2E | Playwright (Chromium) | La demo completa en un navegador real, de la adhesión hasta el usuario notificado. Falla ante cualquier error en la consola del navegador | `make e2e` |
| Carga | k6 | Ver abajo | `make load` |

## k6: escenarios

Se corren contra el compose levantado, con el **seed de volumen**, no con el de la demo: `make seed-volume n=2000` genera 2.000 clientes activos con casos borde (~70% sin problemas, ~15% con un cobro sin factura, ~10% con una transferencia de una persona desconocida, ~5% cerca del tope).

Los escenarios siguen el mes en orden. `make load-all` corre la secuencia completa sobre un seed de volumen nuevo.

| Escenario | Qué simula | Umbrales | Resultado medido (16/11, laptop, 1 proceso de API y 1 worker con 2 procesos) |
|---|---|---|---|
| `user_activity` | Durante el mes: muchos usuarios cobrando a la vez. Cada evento es un movimiento que llega de Wallbit y se clasifica en el momento. Si la app le pregunta algo al usuario, la mayoría responde o factura en el acto | p95 < 500 ms (facturar < 800 ms), errores < 1%, sin iteraciones descartadas | **50 eventos/s:** p95 de 23 ms. Ver el límite abajo |
| `month_close_burst` | El día 1: dispara el cierre y espera a que los 2.000 estén calculados | 100% en < 10 min, cola de mensajes muertos vacía | **15–20 s**. Resultado: 1.522 listos, 281 en revisión, 197 esperando al usuario |
| `late_answers` | Entre el día 1 y el 5: todos los usuarios con una pregunta pendiente la responden a la vez (20 en paralelo). Cada respuesta recalcula su cierre | p95 < 500 ms, todo recalculado en < 2 min | **478 respuestas en 6,9 s.** p95: responder 342 ms, facturar 355 ms. Todo recalculado **7,9 s** después de la primera respuesta |
| `day_5_expiry` | El día 5 (de madrugada del 6): vencen las preguntas sin respuesta y se recalculan todos los cierres abiertos | 100% en < 10 min | **1.956 cierres recalculados en 17 s.** Los 197 que esperaban al usuario pasan a revisión |
| `accountant_inbox` | 5 contadores durante 1 minuto: bandeja, detalle y vista previa del mensaje | p95 < 300 ms por pantalla, errores < 1% | p95: bandeja **115 ms**, detalle **31 ms**, vista previa **14 ms** |
| `accountant_workday` | 5 contadores revisan los 478 cierres en revisión: abren, leen, a veces le escriben al usuario, resuelven o clasifican y aprueban. Al final aprueban en lote los listos | p95 < 300 ms al leer, < 500 ms al actuar, lote < 10 s | p95: detalle **29 ms**, resolver o clasificar **87 ms**, aprobar **35 ms**. El sistema suma **0,2 s por revisión completa** (p95). Lote: **1.522 cierres en 4,0 s** |

En todas las corridas: 0 errores y cola de mensajes muertos vacía.

```bash
make seed-volume n=2000
make load scenario=user_activity rate=50 duration=1m
make load scenario=month_close_burst
make load scenario=late_answers
make load scenario=day_5_expiry
make load scenario=accountant_workday vus=5
make load scenario=accountant_inbox
make seed            # volver a los datos de la demo
```

### Límite de la actividad de los usuarios durante el mes

`user_activity` a tasa fija, subiendo hasta que deja de cumplir los umbrales:

| Procesos de API | Eventos por segundo | p95 | Resultado |
|---|---|---|---|
| 1 | 50 | 23 ms | ✅ |
| 1 | 75 | 3,5 s | ❌ satura en ~57 eventos/s |
| 4 | 100 | 294 ms | ✅ |
| 4 | 150 | 278 ms | ✅ |
| 4 | 200 | 3,6 s | ❌ satura en ~150 eventos/s |

- **Un proceso aguanta ~55 eventos/s**, unos 90 requests/s contando las respuestas de los usuarios. Es CPU de Python en un solo proceso.
- **Escala con procesos:** con 4 procesos, ~150 eventos/s. Es casi 3 veces más, en la misma laptop que además corre Postgres.
- **Lectura de negocio:** 2.000 usuarios con ~10 movimientos al mes son ~20.000 eventos por mes. Aun si todos llegaran en la misma hora, serían ~6 por segundo. Un proceso de API alcanza para ~10 veces la base actual en esa hora pico.

**Lo que encontró esta prueba (corregido):**

1. **La API se congelaba a 100 eventos/s y no se recuperaba.**
   - **Causa:** FastAPI corre los endpoints síncronos y la validación de sus respuestas en un mismo pool de 40 threads. Con 40 requests esperando una de las 10 conexiones a la base, los 10 que tenían conexión no conseguían thread para terminar.
   - **Fix:** un middleware admite tantos requests en vuelo como conexiones tiene el pool. El resto espera en el event loop.
   - **Resultado:** bajo sobrecarga sube la latencia, pero no hay caída.
2. **Carrera entre dos escrituras del mismo cliente.** Pasaba con un cobro que llegaba mientras el usuario respondía: los dos clasificaban los mismos movimientos y uno fallaba por clave única.
   - **Fix:** un lock por cliente (advisory lock de Postgres), tomado primero por cada caso de uso que escribe.
   - **De paso:** el día 5 ya no vence todas las preguntas en una transacción. Las vence cada recálculo, bajo el lock de su cliente, y así se evita un deadlock con un usuario respondiendo en ese momento.

Bajo sobrecarga quedan algunos `409 prompt_closed`: el usuario responde una pregunta que otro evento ya resolvió. Es el comportamiento correcto.

**Corridas descartadas:** tres corridas largas dieron entre 950 y 1.065 s. Los logs de todos los servicios muestran huecos de ~16 minutos sin actividad: la laptop se suspendió en medio de la corrida. Al repetirlas sin suspensión dieron 19,6 s (día 1) y 17 s (día 5).

## Medir el trabajo del contador

El cuello real es el contador, no el cálculo. Se mide en tres niveles:

1. **En producción, con datos reales: dashboard *Productividad del contador*** (Grafana).
   - La consola registra en la auditoría `close.viewed` cada vez que el contador abre un cierre.
   - **Tiempo de revisión** = desde la última apertura hasta la aprobación, mediana y p90. Solo cuenta los cierres aprobados uno por uno; las aperturas de más de 2 horas se descartan (pestaña abandonada).
   - **% que necesitó al contador** = aprobados uno por uno sobre el total.
   - **Capacidad** = horas de revisión al mes ÷ (minutos por revisión × % que necesita al contador). Las horas son una variable del dashboard (por defecto 16).
   - **Otros paneles:** clientes por contador hoy, horas desde el día 1 hasta el último aviso y acciones por contador.
2. **Modelo de capacidad (la estimación de la propuesta):**
   - Con 2.000 clientes, 478 caen en revisión (24%).
   - A 3,5 minutos por revisión son ~28 horas por mes.
   - Con 16 horas de revisión al mes, un contador atiende ~1.100 clientes. Si las reglas globales y las respuestas en el momento bajan la revisión al 10%, atiende ~2.700.
3. **k6 `accountant_workday`:** mide lo que agrega el sistema a cada revisión (0,2 s), no el tiempo humano. Confirma que el software no es el cuello: el tiempo de revisión es todo del contador.

**Pendiente:** test de usabilidad con un contador real, con tareas cronometradas (revisar 20 cierres con casos variados) y el dashboard como medición.

Con k6 los tiempos de revisión salen en décimas de segundo, porque es un robot, y la capacidad da cifras irreales. Para ver el dashboard con datos humanos, hay que recorrer la demo en la consola.

### Límite de escala de la ráfaga del día 1

Medido el 16/11 en una laptop: Docker con 8 CPU y 4 GB. Postgres con la configuración por defecto (128 MB de cache).

| Clientes | Workers (2 procesos c/u) | Tiempo | Cierres por segundo | Resultado |
|---|---|---|---|---|
| 2.000 | 1 | 15,2 s | 131 | ✅ |
| 10.000 | 1 | 104,8 s | 95 | ✅ |
| 10.000 | 3 | 63,0 s | 159 | ✅ |
| 25.000 | 1 | 532,5 s | 47 | ✅ justo bajo los 10 min |
| 25.000 | 3 | 361,9 s | 69 | ✅ |
| 50.000 | 3 | > 21 min (30.356 calculados) | ~24 | ❌ no llega |

Lecturas:

- **El límite con este código, en esta máquina, ronda los 25–30 mil clientes** para cerrar el día 1 en menos de 10 minutos. Son 10 a 15 veces los 2.000 usuarios de hoy.
- **Escalar workers ayuda, pero no de forma lineal:** triplicarlos dio 1,5–1,7x. En plena carga cada worker usa ~120–140% de CPU y Postgres ~170%, así que la laptop entera queda saturada. Ya no hay margen de hardware para medir más allá.
- **El rendimiento cae a medida que crece el volumen, y no debería.** Las tareas usan índices (cero lecturas secuenciales en `invoices`, `movements` y `movement_classifications`), así que el costo por cierre debería ser constante.
  - **Causa confirmada:** el monitoreo, que recorría tablas enteras en cada scrape. Las métricas de negocio cargaban todos los clientes en memoria; ya están corregidas para contar en SQL.
  - **Sospechosa:** la base (594 MB con 50.000 clientes) excede la cache de Postgres.
- **Prueba con más cache (1 GB), no concluyente:** salió peor (25.000 sin terminar en 17 min), probablemente por arrancar Postgres en frío y por la presión de memoria en una máquina virtual de 4 GB. La configuración se revirtió.

Próximo paso, antes de producción:

1. **Medir dónde se va el tiempo de cada cálculo**, que hoy es CPU de Python en el worker. Después, bajar consultas por cierre (cargar en lote las facturas y las declaraciones del período).
2. **Infraestructura:** Postgres en su propia máquina con memoria acorde, PgBouncer y más workers.
3. **Separar el monitoreo de la base principal**, con una réplica de lectura o métricas precalculadas.

De todos modos, el día 1 no necesita terminar en 10 minutos (el objetivo que nos pusimos): la ventana real es el día, y lo que limita al servicio es el contador, no el cálculo.

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
- **Exportar los resultados de k6 a Prometheus**, con un dashboard "Load tests".
- **Más en la CI:** umbral de cobertura (dominio ≥ 95%), chequear que el cliente del OpenAPI no quedó desactualizado, k6 corto en cada push a `dev` y k6 completo nightly.
