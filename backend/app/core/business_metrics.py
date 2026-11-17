"""Business metrics for the "Cierre del mes" dashboard, computed from the DB at scrape time.

Counting at scrape time (every 15 s) keeps the numbers exact and free of drift: they are read
from the source of truth instead of being incremented in many code paths.
"""

from collections.abc import Iterator

import structlog
from prometheus_client.core import GaugeMetricFamily
from prometheus_client.registry import Collector
from sqlalchemy import bindparam, case, func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.db import SessionLocal
from app.modules.clients.models import Client
from app.modules.closing.models import AlertStatus, CloseAlert, PeriodClose
from app.modules.notifications.models import Notification
from app.modules.prompts.models import PromptStatus, UserPrompt
from app.modules.review.models import CloseSnapshot

log = structlog.get_logger()


class BusinessMetricsCollector(Collector):
    def collect(self) -> Iterator[GaugeMetricFamily]:
        try:
            yield from self._collect()
        except SQLAlchemyError as exc:  # never break /metrics because the DB hiccupped
            log.warning("business_metrics.unavailable", error=str(exc))

    def _collect(self) -> Iterator[GaugeMetricFamily]:
        with SessionLocal() as s:
            closes = GaugeMetricFamily(
                "cierre_closes", "Cierres por período y estado", labels=["period", "status"]
            )
            for period, status, n in s.execute(
                select(PeriodClose.period, PeriodClose.status, func.count()).group_by(
                    PeriodClose.period, PeriodClose.status
                )
            ):
                closes.add_metric([period, status.value], n)
            yield closes

            dirty = GaugeMetricFamily(
                "cierre_closes_dirty", "Cierres esperando recálculo", labels=["period"]
            )
            for period, n in s.execute(
                select(PeriodClose.period, func.count())
                .where(PeriodClose.dirty.is_(True))
                .group_by(PeriodClose.period)
            ):
                dirty.add_metric([period], n)
            yield dirty

            alerts = GaugeMetricFamily(
                "cierre_alerts_open",
                "Alertas abiertas por tipo y severidad",
                labels=["period", "type", "severity"],
            )
            for period, kind, severity, n in s.execute(
                select(PeriodClose.period, CloseAlert.type, CloseAlert.severity, func.count())
                .join(PeriodClose, PeriodClose.id == CloseAlert.close_id)
                .where(CloseAlert.present.is_(True), CloseAlert.status == AlertStatus.OPEN)
                .group_by(PeriodClose.period, CloseAlert.type, CloseAlert.severity)
            ):
                alerts.add_metric([period, kind.value, severity.value], n)
            yield alerts

            resolved = GaugeMetricFamily(
                "cierre_alerts_resolved",
                "Alertas resueltas por el contador",
                labels=["period", "type"],
            )
            for period, kind, n in s.execute(
                select(PeriodClose.period, CloseAlert.type, func.count())
                .join(PeriodClose, PeriodClose.id == CloseAlert.close_id)
                .where(CloseAlert.status == AlertStatus.RESOLVED)
                .group_by(PeriodClose.period, CloseAlert.type)
            ):
                resolved.add_metric([period, kind.value], n)
            yield resolved

            prompts = GaugeMetricFamily(
                "cierre_user_prompts",
                "Avisos al usuario por tipo y estado",
                labels=["period", "kind", "status"],
            )
            for period, kind, status, n in s.execute(
                select(
                    UserPrompt.period, UserPrompt.kind, UserPrompt.status, func.count()
                ).group_by(UserPrompt.period, UserPrompt.kind, UserPrompt.status)
            ):
                prompts.add_metric([period, kind.value, status.value], n)
            yield prompts

            stage = GaugeMetricFamily(
                "cierre_clients", "Usuarios por etapa de adhesión", labels=["stage"]
            )
            # Counted in SQL: loading every client into memory grows with the user base.
            stage_expr = case(
                (Client.enrolled_at.is_(None), "offer"),
                (Client.arca_linked_at.is_(None), "link_arca"),
                else_="active",
            )
            counts = {"offer": 0, "link_arca": 0, "active": 0}
            for key, n in s.execute(select(stage_expr, func.count()).group_by(stage_expr)):
                counts[key] = n
            for key, n in counts.items():
                stage.add_metric([key], n)
            yield stage

            approvals = GaugeMetricFamily(
                "cierre_approvals",
                "Cierres aprobados por modo (individual o en lote)",
                labels=["period", "mode"],
            )
            for period, batch, n in s.execute(
                select(
                    CloseSnapshot.period, CloseSnapshot.batch_key.is_not(None), func.count()
                ).group_by(CloseSnapshot.period, CloseSnapshot.batch_key.is_not(None))
            ):
                approvals.add_metric([period, "batch" if batch else "individual"], n)
            yield approvals

            notifications = GaugeMetricFamily(
                "cierre_notifications", "Notificaciones por estado", labels=["status"]
            )
            for status, n in s.execute(
                select(Notification.status, func.count()).group_by(Notification.status)
            ):
                notifications.add_metric([status.value], n)
            yield notifications

            pending = GaugeMetricFamily(
                "cierre_user_prompts_open_total", "Avisos abiertos esperando al usuario"
            )
            pending.add_metric(
                [],
                s.scalar(
                    select(func.count())
                    .select_from(UserPrompt)
                    .where(UserPrompt.status == PromptStatus.OPEN)
                )
                or 0,
            )
            yield pending

            yield from _productivity(s)


# What counts as accountant work. Users act as `client:<id>` and never appear here.
ACCOUNTANT_ACTIONS = (
    "close.viewed",
    "alert.resolved",
    "alert.reopened",
    "movement.classified_by_accountant",
    "movement.override_removed",
    "alert.message_posted",
    "close.approved",
    "close.batch_approved",
)
# A view older than this before the approval is an abandoned tab, not a review.
MAX_REVIEW_SECONDS = 2 * 3600

# Review time of an individually approved close: from the accountant's last view of it to the
# approval. Batch approvals are excluded (they take no per-close time).
REVIEW_SECONDS = text(
    """
    WITH sessions AS (
      SELECT s.period,
             EXTRACT(EPOCH FROM s.approved_at - (
               SELECT max(e.created_at) FROM audit_events e
               WHERE e.action = 'close.viewed' AND e.period = s.period
                 AND e.entity_id = s.close_id AND e.actor = s.approved_by
                 AND e.created_at <= s.approved_at)) AS seconds
      FROM close_snapshots s
      WHERE s.batch_key IS NULL
    )
    SELECT period, count(*), avg(seconds),
           percentile_cont(0.5) WITHIN GROUP (ORDER BY seconds),
           percentile_cont(0.9) WITHIN GROUP (ORDER BY seconds)
    FROM sessions
    WHERE seconds IS NOT NULL AND seconds <= :max_seconds
    GROUP BY period
    """
)

ACTIONS_BY_ACTOR = text(
    """
    SELECT period, actor, action, count(*) FROM audit_events
    WHERE action IN :actions AND period IS NOT NULL AND actor NOT LIKE 'client:%'
    GROUP BY period, actor, action
    """
).bindparams(bindparam("actions", expanding=True))

# Hours from the start of the close (day 1) to the last approval and the last notification.
MILESTONES = text(
    """
    SELECT pc.period,
           EXTRACT(EPOCH FROM max(s.approved_at) - min(pc.created_at)) / 3600,
           EXTRACT(EPOCH FROM max(n.sent_at) - min(pc.created_at)) / 3600
    FROM period_closes pc
    LEFT JOIN close_snapshots s ON s.close_id = pc.id
    LEFT JOIN notifications n ON n.snapshot_id = s.id
    GROUP BY pc.period
    """
)


def _productivity(s: Session) -> Iterator[GaugeMetricFamily]:
    review = GaugeMetricFamily(
        "cierre_review_seconds",
        "Tiempo de revisión por cierre aprobado uno por uno (última apertura → aprobación)",
        labels=["period", "stat"],
    )
    for period, n, avg, p50, p90 in s.execute(REVIEW_SECONDS, {"max_seconds": MAX_REVIEW_SECONDS}):
        review.add_metric([period, "count"], n)
        review.add_metric([period, "avg"], float(avg))
        review.add_metric([period, "p50"], float(p50))
        review.add_metric([period, "p90"], float(p90))
    yield review

    actions = GaugeMetricFamily(
        "cierre_accountant_actions",
        "Acciones del contador por período, persona y tipo",
        labels=["period", "actor", "action"],
    )
    for period, actor, action, n in s.execute(ACTIONS_BY_ACTOR, {"actions": ACCOUNTANT_ACTIONS}):
        actions.add_metric([period, actor, action], n)
    yield actions

    milestones = GaugeMetricFamily(
        "cierre_period_hours",
        "Horas desde el inicio del cierre (día 1) hasta cada hito",
        labels=["period", "milestone"],
    )
    for period, last_approval, last_notification in s.execute(MILESTONES):
        if last_approval is not None:
            milestones.add_metric([period, "last_approval"], float(last_approval))
        if last_notification is not None:
            milestones.add_metric([period, "last_notification"], float(last_notification))
    yield milestones
