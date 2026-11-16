"""Celery app + Beat.

Messages carry ids only: Postgres is the source of truth (ARCHITECTURE §5).
"""

from typing import Any

from celery import Celery
from celery.schedules import crontab
from celery.signals import worker_ready
from kombu import Exchange, Queue  # type: ignore[attr-defined]

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery("cierre", broker=settings.rabbitmq_url)

dlx = Exchange("dlx", type="fanout")
dead_letter = Queue("dead_letter", dlx)


def _queue(name: str) -> Queue:
    return Queue(
        name,
        Exchange(name, type="direct"),
        routing_key=name,
        queue_arguments={
            "x-dead-letter-exchange": "dlx",
            "x-dead-letter-routing-key": f"{name}.dead",
        },
    )


celery_app.conf.update(
    task_queues=[
        _queue("closing"),
        _queue("recompute"),
        _queue("notifications"),
    ],
    task_default_queue="recompute",
    task_routes={
        "closing.*": {"queue": "closing"},
        "recompute.*": {"queue": "recompute"},
        "notifications.*": {"queue": "notifications"},
    },
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_ignore_result=True,  # progress is read from the DB, not a result backend
    task_serializer="json",
    accept_content=["json"],
    worker_send_task_events=True,  # for Flower and celery-exporter
    task_send_sent_event=True,
    timezone=settings.business_timezone,
    enable_utc=True,
    beat_schedule={
        "start-period-close": {
            "task": "closing.start_period_close",
            "schedule": crontab(minute=5, hour=0, day_of_month=1),
        },
        "expire-pending-confirmations": {
            "task": "closing.expire_pending_confirmations",
            "schedule": crontab(minute=0, hour=0, day_of_month=6),
        },
        "sweep-dirty-closes": {
            "task": "recompute.sweep_dirty_closes",
            "schedule": crontab(minute="*/5"),
        },
        "sweep-pending-notifications": {
            "task": "notifications.sweep_pending",
            "schedule": crontab(minute="*/5"),
        },
        "send-due-reminders": {
            "task": "notifications.send_due_reminders",
            "schedule": crontab(minute=0, hour=10, day_of_month=17),
        },
    },
)


@worker_ready.connect
def declare_dead_letter_queue(sender: Any, **_: Any) -> None:
    """No worker consumes the DLQ; declare it so dead messages are not lost."""
    with sender.app.connection_for_write() as conn:
        dead_letter.bind(conn).declare()


celery_app.autodiscover_tasks(["app.modules.closing", "app.modules.notifications"])

app = celery_app
