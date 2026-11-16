# Flujo general — Cierre de mes

## 1. Quién hace qué

| Herramienta (automático) | Contador (excepciones + firma) | Usuario (app Wallbit) |
|---|---|---|
| Importa las facturas de ARCA y dispara el cierre el día 1 para todos los clientes | Revisa solo los cierres `IN_REVIEW` | Adhiere al servicio: consentimiento + **vincula ARCA (obligatorio)** |
| Clasifica movimientos con reglas globales y match con facturas de ARCA | Valida por excepción, resuelve lo que el usuario no aclaró y crea reglas globales | Responde qué es cada contraparte desconocida |
| Calcula facturado, cobrado, acumulado 12 meses, cuota y vencimiento | Aprueba en lote los `READY` | Responde al contador; si falta una factura, la emite desde la app ("Facturar este cobro") |
| Detecta alertas y asigna estado | Reabre un cierre aprobado si hace falta (con motivo) | Recibe el aviso aprobado: facturado, a pagar, vencimiento |
| Recalcula cuando llega un dato nuevo | Mantiene parámetros fiscales y plantillas de mensajes | Recibe recordatorio antes del vencimiento |
| Congela snapshot, registra auditoría y notifica | | |

## 2. Flujo de punta a punta

```mermaid
flowchart TD
  subgraph USR0["Usuario: adhesión (una vez)"]
    O1["Ve la oferta en el inicio de Wallbit"] --> O2["Adhiere: consentimiento + datos fiscales"]
    O2 --> O3["Vincula ARCA (obligatorio)"]
  end

  subgraph SYS["Sistema"]
    O3 --> IMP["Importa comprobantes de ARCA"]
    IMP --> CL["Clasifica cada movimiento al llegar (match con ARCA)"]
    MV["Movimiento nuevo durante el mes"] --> CL
    CL -- "cobro sin factura" --> NUD["Aviso: Facturar este cobro"]
    CL -- "desconocido" --> ASKQ["Pregunta: ¿Quién es…?"]
    A["Día 1: Celery Beat dispara start_period_close"] --> B["Fan-out: compute_client_close por cliente"]
    CL -.-> C
    B --> C["Consolida clasificaciones del mes"]
    C --> D["Motor fiscal: facturado, cobrado, acumulado 12m, cuota"]
    D --> E["Evaluar alertas"]
    E --> H{"¿Bloqueantes del contador?"}
    H -- Sí --> J["IN_REVIEW"]
    H -- No --> P{"¿Preguntas abiertas al usuario?"}
    P -- Sí --> G["PENDING_DATA"]
    P -- No --> I["READY"]
    R["Recalcular (idempotente)"] --> D
    S["APPROVED: snapshot inmutable + audit log"] --> N["Notificar desde el snapshot"]
    N --> O["NOTIFIED"]
    O --> REM["Día 17: recordatorio de vencimiento"]
  end

  subgraph USR["Usuario (app)"]
    U1["Responde “¿Quién es?”"]
    U2["Responde al contador / “Facturar este cobro”"]
    U3["Ve su cierre: facturado, a pagar, vencimiento"]
  end

  subgraph ACC["Contador (consola web)"]
    K["Bandeja del período"] --> L["Resuelve excepciones: conversación, reclasifica, regla global"]
    K --> M["Aprueba en lote los READY"]
    G2["Día 5: vencen las preguntas"] --> L
  end

  NUD --> U2
  ASKQ --> U1
  G --> U1
  G -. día 5 sin respuesta .-> G2
  L --> U2
  U1 --> R
  U2 --> R
  L --> R
  I --> K
  J --> K
  M --> S
  L -- aprueba individual --> S
  O --> U3
  REM --> U3
```

## 3. Secuencia técnica

Postgres es la fuente de verdad; los mensajes solo llevan ids. Toda escritura de estado va con su evento de auditoría en la misma transacción, y se encola recién después del commit.

```mermaid
sequenceDiagram
  autonumber
  participant Beat as Celery Beat
  participant Q as RabbitMQ
  participant W as Worker
  participant DB as Postgres
  participant API as FastAPI
  participant U as Usuario (mobile)
  participant C as Contador (web)

  Beat->>Q: start_period_close("2026-10")
  Q->>W: crear period_close por cliente (ON CONFLICT DO NOTHING)
  W->>Q: compute_client_close x N (cola closing)
  Q->>W: calcular cliente
  W->>DB: leer movimientos, facturas, declaraciones, parámetros
  W->>DB: TX: resultado + traza + alertas + estado + audit
  U->>API: vincular ARCA, declarar contraparte o emitir factura
  API->>DB: TX: dato + cierre dirty + audit
  API->>Q: después del commit: recompute_client_close (cola recompute)
  Q->>W: recalcular
  W->>DB: TX: SELECT FOR UPDATE, recalcular, limpiar dirty + audit
  C->>API: POST /classifications/bulk (Idempotency-Key)
  API->>DB: TX: clasificaciones + dirty + audit por cliente
  API->>Q: recompute_client_close x clientes afectados
  C->>API: POST /period-closes/batch-approve (Idempotency-Key)
  API->>DB: TX por ~100: snapshot + APPROVED + notification pendiente + audit
  API->>Q: send_close_notification(notification_id) (cola notifications)
  Q->>W: enviar si sigue pendiente
  W->>DB: TX: notificación enviada + NOTIFIED + audit
  Beat->>Q: cada 5 min: sweep dirty + notificaciones pendientes
  Beat->>Q: día 5: expire_pending_questions
  U->>API: GET /clients/{id}/period-closes/2026-10
```

## 4. Estados del cierre (por cliente y período)

```mermaid
stateDiagram-v2
  [*] --> PENDING_DATA: cálculo preliminar
  PENDING_DATA --> COMPUTED: usuario responde
  PENDING_DATA --> IN_REVIEW: vence plazo, decide el contador
  COMPUTED --> READY: sin bloqueantes
  COMPUTED --> IN_REVIEW: con bloqueantes
  IN_REVIEW --> COMPUTED: dato nuevo o corrección
  READY --> COMPUTED: dato nuevo
  IN_REVIEW --> READY: contador resuelve
  READY --> APPROVED: aprobación individual o en lote
  APPROVED --> NOTIFIED: notificación enviada
  APPROVED --> IN_REVIEW: reabrir con motivo
  NOTIFIED --> IN_REVIEW: reabrir con motivo
  NOTIFIED --> [*]
```

## 5. Clasificación por capas (sin reglas por cliente)

```mermaid
flowchart TD
  M["Movimiento"] --> L1{"¿Tipo estructural?<br/>conversión, tarjeta, interés, interna"}
  L1 -- Sí --> OK1["Clasificado: estructural"]
  L1 -- No --> L2{"¿Regla global?"}
  L2 -- Sí --> OK2["Clasificado: regla global"]
  L2 -- No --> L3{"¿Matchea factura de ARCA?"}
  L3 -- Sí --> OK3["service_income + vínculo a factura"]
  L3 -- No --> L4{"¿El usuario ya declaró<br/>esta contraparte?"}
  L4 -- Sí --> OK4["Clasificado: declaración del usuario"]
  L4 -- No --> SG["Suggester: sugerencia (heurística; futuro ML)"]
  SG --> ASK["Pregunta al usuario, una por contraparte"]
  ASK -- "Responde" --> RISK{"¿No facturable con<br/>señales de riesgo?"}
  RISK -- No --> OK4
  RISK -- Sí --> ALR["Alerta al contador"]
  ASK -- "Día 5 sin respuesta / Otro" --> UN["Sin clasificar: alerta bloqueante"]
  UN --> CT["Contador resuelve en 'Resolver por alerta'"]
  ALR --> CT
  CT --> Q{"¿Guardar como regla global?"}
  Q -- Sí --> NR["Nueva regla global"]
```

El contador no mantiene reglas por cliente: lo que solo sabe el usuario lo declara el usuario (una vez por contraparte) y el contador valida por excepción. Cada respuesta y cada validación queda como etiqueta para un modelo ML local futuro.

## 6. Calendario del cierre (ej. cierre de octubre 2026)

| Día de noviembre | Evento |
|---|---|
| 1–31 (mes en curso) | Cada movimiento se clasifica al llegar: avisos “Facturar este cobro” y preguntas “¿Quién es?” en el momento |
| 1 | Consolidación: motor fiscal, alertas y estado con las clasificaciones del mes |
| 1–5 | Usuarios responden o facturan desde la app → recálculos. Contador trabaja excepciones |
| 5 | Vence el plazo de las preguntas; las pendientes pasan al contador |
| 5–7 | Aprobación en lote y notificación |
| 17 | Recordatorio de vencimiento |
| 20 | Vencimiento de la cuota de monotributo |
