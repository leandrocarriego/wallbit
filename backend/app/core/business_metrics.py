"""Business metrics for the "Cierre del mes" dashboard, computed from the DB at scrape time.

Counting at scrape time (every 15 s) keeps the numbers exact and free of drift: they are read
from the source of truth instead of being incremented in many code paths.
"""

from collections.abc import Iterator

import structlog
from prometheus_client.core import GaugeMetricFamily
from prometheus_client.registry import Collector
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

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
            counts = {"offer": 0, "link_arca": 0, "active": 0}
            for c in s.scalars(select(Client)):
                key = "offer" if c.enrolled_at is None else "active" if c.is_active else "link_arca"
                counts[key] += 1
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
