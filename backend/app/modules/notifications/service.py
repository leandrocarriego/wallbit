"""Render the approved-close message from the active template and deliver it in-app."""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.audit.service import record
from app.modules.notifications.models import (
    Notification,
    NotificationStatus,
    NotificationTemplate,
)

CLOSE_APPROVED = "close_approved"
MONTHS = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]  # fmt: skip


def active_template(session: Session, name: str = CLOSE_APPROVED) -> NotificationTemplate:
    template = session.scalars(
        select(NotificationTemplate)
        .where(NotificationTemplate.name == name, NotificationTemplate.active.is_(True))
        .order_by(NotificationTemplate.version.desc())
    ).first()
    if template is None:
        raise RuntimeError(f"No hay una plantilla aprobada para {name}")
    return template


def _ars(value: Decimal) -> str:
    return f"$ {value:,.0f}".replace(",", ".")


def _usd(value: Decimal) -> str:
    text = f"{value:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return f"USD {text.removesuffix(',00')}"


def render_close_message(
    template: NotificationTemplate, *, first_name: str, period: str, result: dict[str, Any]
) -> str:
    """Fill the template with the snapshot figures. The accountant approved the template."""
    month = MONTHS[int(period.split("-")[1]) - 1]
    due = date.fromisoformat(result["due_date"])
    lines = template.body.format(
        nombre=first_name,
        mes=month,
        facturado_usd=_usd(Decimal(result["invoiced_by_currency"].get("USD", "0"))),
        facturado_ars=_ars(Decimal(result["invoiced_ars"])),
        cuota=_ars(Decimal(result["monthly_fee_ars"])),
        vencimiento=f"{due:%d/%m}",
    )
    if Decimal(result["cap_usage_pct"]) >= 80 and not result["exceeds_category"]:
        lines += (
            f"\nLlevás el {Decimal(result['cap_usage_pct']):.0f}% del tope de tu categoría. "
            "Si lo superás, te avisamos para recategorizarte."
        )
    if result["exceeds_category"]:
        lines += (
            f"\nSuperaste el tope de tu categoría: corresponde pasar a la "
            f"{result['required_category']}. Tu contador te va a contactar."
        )
    return lines


def send(session: Session, notification_id: uuid.UUID, *, actor: str) -> Notification:
    """Deliver once. A retry of an already sent notification does nothing."""
    notification = session.get(Notification, notification_id, with_for_update=True)
    assert notification is not None
    if notification.status is NotificationStatus.SENT:
        return notification
    notification.status = NotificationStatus.SENT
    notification.sent_at = datetime.now(UTC)
    record(
        session,
        actor=actor,
        action="notification.sent",
        entity_type="notification",
        entity_id=notification.id,
        client_id=notification.client_id,
    )
    return notification
