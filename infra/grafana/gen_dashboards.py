"""Generates the provisioned Grafana dashboards. Run: python3 infra/grafana/gen_dashboards.py infra/grafana/dashboards"""
import json, sys

DS = {"type": "prometheus", "uid": "prometheus"}
OUT = sys.argv[1]

def panel(pid, title, kind, x, y, w, h, targets, desc="", **extra):
    # Stats, bars and tables show the current value: instant queries, so a state that no longer
    # exists reads 0 instead of the last value it had.
    instant = kind in ("stat", "bargauge", "table")
    p = {"id": pid, "type": kind, "title": title, "description": desc, "datasource": DS,
         "gridPos": {"x": x, "y": y, "w": w, "h": h},
         "targets": [{"refId": chr(65 + i), "expr": e, "legendFormat": l, "datasource": DS,
                      **({"instant": True, "range": False} if instant else {}),
                      **({"format": "table"} if kind == "table" else {})}
                     for i, (e, l) in enumerate(targets)]}
    p.update(extra)
    return p

def stat(pid, title, x, y, w, expr, desc="", unit="none", thresholds=None, color="fixed:text", h=4):
    steps = thresholds or [{"color": "green", "value": None}]
    return panel(pid, title, "stat", x, y, w, h, [(f"({expr}) or vector(0)", "")], desc,
                 fieldConfig={"defaults": {"unit": unit, "thresholds": {"mode": "absolute", "steps": steps},
                                           "color": {"mode": "thresholds"}, "noValue": "0"}, "overrides": []},
                 options={"reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
                          "colorMode": "value", "graphMode": "none", "textMode": "value", "justifyMode": "center"})

def ts(pid, title, x, y, w, h, targets, desc="", unit="short", stack=False):
    return panel(pid, title, "timeseries", x, y, w, h, targets, desc,
                 fieldConfig={"defaults": {"unit": unit, "custom": {"lineWidth": 2, "fillOpacity": 20 if stack else 8,
                              "stacking": {"mode": "normal" if stack else "none", "group": "A"}, "showPoints": "never"}},
                              "overrides": []},
                 options={"legend": {"displayMode": "list", "placement": "bottom", "showLegend": True},
                          "tooltip": {"mode": "multi", "sort": "desc"}})

def bars(pid, title, x, y, w, h, targets, desc=""):
    return panel(pid, title, "bargauge", x, y, w, h, targets, desc,
                 fieldConfig={"defaults": {"unit": "none", "min": 0, "displayName": "${__series.name}", "noValue": "Ninguna", "thresholds": {"mode": "absolute", "steps": [{"color": "blue", "value": None}]},
                                           "color": {"mode": "thresholds"}}, "overrides": []},
                 options={"orientation": "horizontal", "displayMode": "basic", "showUnfilled": True,
                          "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False}, "valueMode": "color"})

def row(pid, title, y):
    return {"id": pid, "type": "row", "title": title, "collapsed": False, "gridPos": {"x": 0, "y": y, "w": 24, "h": 1}, "panels": []}

def dashboard(uid, title, desc, panels, variables=(), refresh="10s"):
    return {"uid": uid, "title": title, "description": desc, "tags": ["cierre"], "timezone": "browser",
            "schemaVersion": 39, "version": 1, "editable": True, "refresh": refresh, "graphTooltip": 1,
            "time": {"from": "now-1h", "to": "now"}, "templating": {"list": list(variables)},
            "annotations": {"list": []}, "panels": panels, "links": [
                {"title": "Cierre del mes", "type": "link", "url": "/d/cierre-negocio"},
                {"title": "Plataforma", "type": "link", "url": "/d/cierre-plataforma"}]}

RED = [{"color": "green", "value": None}, {"color": "red", "value": 1}]
AMBER = [{"color": "green", "value": None}, {"color": "orange", "value": 1}]
P = '{period="$period"}'
period_var = {"name": "period", "label": "Período", "type": "query", "datasource": DS,
              "query": {"query": "label_values(cierre_closes, period)", "refId": "period"},
              "definition": "label_values(cierre_closes, period)", "refresh": 2, "sort": 2,
              "current": {}, "includeAll": False, "multi": False}

business = dashboard("cierre-negocio", "Cierre del mes",
    "Avance del cierre mensual y carga del contador. Datos leídos de Postgres en cada scrape.", [
    row(1, "Avance", 0),
    stat(2, "Usuarios activos", 0, 1, 4, 'sum(cierre_clients{stage="active"})', "Adheridos y con ARCA vinculado."),
    stat(3, "En revisión", 4, 1, 4, f'sum(cierre_closes{{period="$period",status="IN_REVIEW"}})', "Le toca al contador.", thresholds=RED),
    stat(4, "Esperando usuario", 8, 1, 4, f'sum(cierre_closes{{period="$period",status="PENDING_DATA"}})', "Preguntas abiertas hasta el día 5.", thresholds=AMBER),
    stat(5, "Listos para el lote", 12, 1, 4, f'sum(cierre_closes{{period="$period",status="READY"}})'),
    stat(6, "Notificados", 16, 1, 4, f'sum(cierre_closes{{period="$period",status="NOTIFIED"}})'),
    stat(7, "% notificado", 20, 1, 4,
         f'100 * sum(cierre_closes{{period="$period",status="NOTIFIED"}}) / sum(cierre_closes{P})',
         "Objetivo: 100% antes del día 7.", unit="percent",
         thresholds=[{"color": "red", "value": None}, {"color": "orange", "value": 50}, {"color": "green", "value": 100}]),
    ts(8, "Cierres por estado", 0, 5, 16, 8, [(f'sum by (status) (cierre_closes{P})', "{{status}}")],
       "Cómo avanza el período: de esperando usuario / en revisión a listos, aprobados y notificados.", stack=True),
    bars(9, "Usuarios por etapa de adhesión", 16, 5, 8, 8, [('sum by (stage) (cierre_clients)', "{{stage}}")],
         "offer: vio la oferta · link_arca: adhirió, falta ARCA · active: con contador."),
    row(10, "Carga del contador", 13),
    bars(11, "Alertas abiertas por tipo", 0, 14, 8, 8, [(f'sum by (type) (cierre_alerts_open{P})', "{{type}}")],
         "Lo que todavía bloquea o informa en los cierres del período."),
    stat(12, "Alertas bloqueantes abiertas", 8, 14, 4, f'sum(cierre_alerts_open{{period="$period",severity="blocking"}})', thresholds=RED, h=4),
    stat(13, "Cierres recalculándose", 8, 18, 4, f'sum(cierre_closes_dirty{P})', "Marcados para recálculo; el barrido los recupera cada 5 min.", thresholds=AMBER, h=4),
    bars(14, "Alertas resueltas por el contador", 12, 14, 6, 8, [(f'sum by (type) (cierre_alerts_resolved{P})', "{{type}}")]),
    bars(15, "Aprobaciones por modo", 18, 14, 6, 8, [(f'sum by (mode) (cierre_approvals{P})', "{{mode}}")],
         "Cuánto sale en lote versus uno por uno: la palanca de escala."),
    row(16, "Usuario y avisos", 22),
    panel(17, "Avisos al usuario (Facturar este cobro / ¿Quién es?)", "table", 0, 23, 12, 7,
          [(f'sum by (kind, status) (cierre_user_prompts{P})', "")],
          "answered: el usuario resolvió en el momento · expired: pasó al contador el día 5 · resolved: ya no hacía falta.",
          options={"showHeader": True},
          transformations=[{"id": "organize", "options": {"excludeByName": {"Time": True},
                            "renameByName": {"kind": "Aviso", "status": "Estado", "Value": "Cantidad"}}}]),
    stat(18, "Avisos abiertos", 12, 23, 6, 'sum(cierre_user_prompts_open_total)', "Esperando que el usuario actúe.", thresholds=AMBER, h=7),
    bars(19, "Notificaciones", 18, 23, 6, 7, [('sum by (status) (cierre_notifications)', "{{status}}")],
         "pending: en cola · sent: entregadas en la app."),
], [period_var])

platform = dashboard("cierre-plataforma", "Plataforma",
    "API, colas, workers de Celery y Postgres. Pensado para la ráfaga del día 1.", [
    row(1, "Estado", 0),
    panel(2, "Servicios", "stat", 0, 1, 12, 4, [('up', "{{job}}")], "1 = Prometheus lo está leyendo.",
          fieldConfig={"defaults": {"mappings": [{"type": "value", "options": {"0": {"text": "caído", "color": "red"}, "1": {"text": "ok", "color": "green"}}}],
                                    "color": {"mode": "thresholds"}, "thresholds": {"mode": "absolute", "steps": [{"color": "red", "value": None}, {"color": "green", "value": 1}]}}, "overrides": []},
          options={"reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False}, "colorMode": "background", "graphMode": "none", "textMode": "value_and_name"}),
    stat(3, "Workers de Celery", 12, 1, 4, 'sum(celery_worker_up)', thresholds=[{"color": "red", "value": None}, {"color": "green", "value": 1}]),
    stat(4, "Mensajes en la DLQ", 16, 1, 4, 'sum(rabbitmq_queue_messages{queue="dead_letter"})', "Debe ser 0: cualquier mensaje acá es una tarea que falló definitivamente.", thresholds=RED),
    stat(5, "Tareas fallidas (1 h)", 20, 1, 4, 'sum(increase(celery_task_failed_total[1h]))', thresholds=RED),
    row(6, "API", 5),
    ts(7, "Requests por ruta", 0, 6, 12, 8, [('sum by (route) (rate(http_requests_total{route!~"/metrics|/health"}[1m]))', "{{route}}")], unit="reqps"),
    ts(8, "Latencia p95 por ruta", 12, 6, 8, 8,
       [('histogram_quantile(0.95, sum by (le, route) (rate(http_request_duration_seconds_bucket{route!~"/metrics|/health"}[5m])))', "{{route}}")],
       "Objetivo de la bandeja: p95 < 300 ms.", unit="s"),
    stat(9, "Errores 5xx", 20, 6, 4, 'sum(rate(http_requests_total{status=~"5.."}[5m])) / clamp_min(sum(rate(http_requests_total[5m])), 1e-9) * 100', unit="percent",
         thresholds=[{"color": "green", "value": None}, {"color": "red", "value": 1}], h=8),
    row(10, "Colas y workers", 14),
    ts(11, "Mensajes esperando por cola", 0, 15, 12, 8,
       [('sum by (queue) (rabbitmq_queue_messages_ready{queue=~"closing|recompute|notifications|dead_letter"})', "{{queue}}")],
       "closing absorbe la ráfaga del día 1; recompute debe drenar en segundos."),
    ts(12, "Tareas completadas por segundo", 12, 15, 12, 8, [('sum by (name) (rate(celery_task_succeeded_total[1m]))', "{{name}}")], unit="ops"),
    ts(13, "Duración p95 por tarea", 0, 23, 12, 8,
       [('histogram_quantile(0.95, sum by (le, name) (rate(celery_task_runtime_bucket[5m])))', "{{name}}")], unit="s"),
    ts(14, "Tareas fallidas y reintentos", 12, 23, 12, 8,
       [('sum by (name) (rate(celery_task_failed_total[5m]))', "fallida · {{name}}"), ('sum by (name) (rate(celery_task_retried_total[5m]))', "reintento · {{name}}")], unit="ops"),
    row(15, "Postgres", 31),
    ts(16, "Conexiones", 0, 32, 12, 7, [('sum(pg_stat_database_numbackends{datname="wallbit"})', "wallbit")],
       "El pool por proceso las mantiene acotadas; PgBouncer en producción."),
    stat(17, "Tamaño de la base", 12, 32, 6, 'max(pg_database_size_bytes{datname="wallbit"})', unit="bytes", h=7),
    stat(18, "Postgres arriba", 18, 32, 6, 'max(pg_up)', thresholds=[{"color": "red", "value": None}, {"color": "green", "value": 1}], h=7),
])

for name, d in [("cierre-del-mes.json", business), ("plataforma.json", platform)]:
    with open(f"{OUT}/{name}", "w") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
        f.write("\n")
print("ok")
