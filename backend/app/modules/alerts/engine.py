"""Close alerts and the resulting status. Pure function.

Each alert has a stable `key` (type + subject) so an accountant's resolution survives
recomputes: if the same alert shows up again, it stays resolved.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum

from app.modules.classification.engine import (
    INVOICE_MEMO_MARKERS,
    Category,
    Classification,
    InvoiceIn,
    MovementIn,
    Source,
)
from app.modules.tax_engine.engine import CloseResult


class Severity(StrEnum):
    BLOCKING = "blocking"  # blocks approval, no exceptions
    WAITING = "waiting"  # waits for the user's answer
    INFO = "info"  # goes in the message, does not block


class AlertType(StrEnum):
    UNBILLED_COLLECTION = "unbilled_collection"
    UNCLASSIFIED = "unclassified"
    NON_BILLABLE_RISK = "non_billable_risk"
    EXCEEDS_CATEGORY = "exceeds_category"
    EXCEEDS_REGIME = "exceeds_regime"
    INVOICED_NOT_COLLECTED = "invoiced_not_collected"
    NEAR_CAP = "near_cap"
    STRONG_VARIATION = "strong_variation"


class CloseStatus(StrEnum):
    PENDING_DATA = "PENDING_DATA"
    IN_REVIEW = "IN_REVIEW"
    READY = "READY"
    APPROVED = "APPROVED"
    NOTIFIED = "NOTIFIED"


@dataclass(frozen=True)
class AlertThresholds:
    near_cap_pct: Decimal = Decimal("80")
    strong_variation_pct: Decimal = Decimal("50")
    risky_non_billable_amount: Decimal = Decimal("1000")


@dataclass(frozen=True)
class Alert:
    key: str
    type: AlertType
    severity: Severity
    title: str
    detail: str
    subject_id: str | None = None
    amount: Decimal | None = None


@dataclass(frozen=True)
class AlertInput:
    movements: Sequence[MovementIn]
    classifications: Sequence[Classification]
    invoices: Sequence[InvoiceIn]
    result: CloseResult
    prior_months_invoiced_ars: Sequence[Decimal]  # last 3 months, for the variation check
    answer_deadline_passed: bool
    thresholds: AlertThresholds = field(default_factory=AlertThresholds)


def _num(value: Decimal, decimals: int = 2) -> str:
    text = f"{value:,.{decimals}f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return text.removesuffix(",00") if decimals == 2 else text


def _money(currency: object, amount: Decimal) -> str:
    return f"{currency} {_num(amount)}"


def evaluate_alerts(data: AlertInput) -> list[Alert]:
    alerts: list[Alert] = []
    movements = {m.id: m for m in data.movements}
    matched_invoices = {c.invoice_id for c in data.classifications if c.invoice_id}

    for c in data.classifications:
        m = movements[c.movement_id]
        if c.billable and c.invoice_id is None:
            alerts.append(
                Alert(
                    key=f"{AlertType.UNBILLED_COLLECTION}:{m.id}",
                    type=AlertType.UNBILLED_COLLECTION,
                    severity=Severity.BLOCKING,
                    title=f"Cobro sin facturar · {_money(m.currency, m.amount)}",
                    detail=f"{m.counterparty_name or 'Sin contraparte'}, {m.occurred_on:%d/%m}. "
                    "No hay una factura en ARCA para este cobro.",
                    subject_id=m.id,
                    amount=m.amount,
                )
            )
        if c.category is Category.UNCLASSIFIED:
            # Before day 5 it is a question for the user; afterwards it goes to the accountant.
            severity = Severity.BLOCKING if data.answer_deadline_passed else Severity.WAITING
            alerts.append(
                Alert(
                    key=f"{AlertType.UNCLASSIFIED}:{m.id}",
                    type=AlertType.UNCLASSIFIED,
                    severity=severity,
                    title=f"Movimiento sin clasificar · {_money(m.currency, m.amount)}",
                    detail=f"Transferencia de “{m.counterparty_name}”, {m.occurred_on:%d/%m}.",
                    subject_id=m.id,
                    amount=m.amount,
                )
            )
        if _risky_non_billable(c, m, data.thresholds):
            alerts.append(
                Alert(
                    key=f"{AlertType.NON_BILLABLE_RISK}:{m.id}",
                    type=AlertType.NON_BILLABLE_RISK,
                    severity=Severity.BLOCKING,
                    title="Declarado no facturable con señales de riesgo · "
                    f"{_money(m.currency, m.amount)}",
                    detail=f"El usuario dijo que “{m.counterparty_name}” es {c.category.value}, "
                    "pero el monto o el memo parecen un cobro por trabajo.",
                    subject_id=m.id,
                    amount=m.amount,
                )
            )

    for inv in data.invoices:
        if inv.id not in matched_invoices:
            alerts.append(
                Alert(
                    key=f"{AlertType.INVOICED_NOT_COLLECTED}:{inv.id}",
                    type=AlertType.INVOICED_NOT_COLLECTED,
                    severity=Severity.INFO,
                    title=f"Facturado sin cobro en Wallbit · {inv.number}",
                    detail="Puede haberse cobrado por fuera de Wallbit.",
                    subject_id=inv.id,
                    amount=inv.amount,
                )
            )

    r = data.result
    if r.exceeds_regime:
        alerts.append(
            Alert(
                key=AlertType.EXCEEDS_REGIME.value,
                type=AlertType.EXCEEDS_REGIME,
                severity=Severity.BLOCKING,
                title="Supera el máximo del régimen",
                detail="Posible exclusión del monotributo: se revisa cliente por cliente.",
            )
        )
    elif r.exceeds_category:
        alerts.append(
            Alert(
                key=AlertType.EXCEEDS_CATEGORY.value,
                type=AlertType.EXCEEDS_CATEGORY,
                severity=Severity.BLOCKING,
                title=f"Supera su categoría ({_num(r.cap_usage_pct, 1)}% del tope {r.category})",
                detail=f"Corresponde recategorizar a {r.required_category}.",
            )
        )
    elif r.cap_usage_pct >= data.thresholds.near_cap_pct:
        alerts.append(
            Alert(
                key=AlertType.NEAR_CAP.value,
                type=AlertType.NEAR_CAP,
                severity=Severity.INFO,
                title=f"Acumulado de 12 meses al {_num(r.cap_usage_pct, 1)}% del tope {r.category}",
                detail="Se incluye en el mensaje al usuario.",
            )
        )

    variation = _variation_pct(r.invoiced_ars, data.prior_months_invoiced_ars)
    if variation is not None and abs(variation) >= data.thresholds.strong_variation_pct:
        alerts.append(
            Alert(
                key=AlertType.STRONG_VARIATION.value,
                type=AlertType.STRONG_VARIATION,
                severity=Severity.INFO,
                title=f"Variación fuerte: {variation:+.0f}% contra el promedio de 3 meses",
                detail="Conviene mirarlo antes de aprobar en lote.",
            )
        )
    return alerts


def derive_status(alerts: Iterable[Alert], resolved_keys: frozenset[str]) -> CloseStatus:
    """Accountant blockers → IN_REVIEW; open questions to the user → PENDING_DATA."""
    open_alerts = [a for a in alerts if a.key not in resolved_keys]
    if any(a.severity is Severity.BLOCKING for a in open_alerts):
        return CloseStatus.IN_REVIEW
    if any(a.severity is Severity.WAITING for a in open_alerts):
        return CloseStatus.PENDING_DATA
    return CloseStatus.READY


def _risky_non_billable(c: Classification, m: MovementIn, t: AlertThresholds) -> bool:
    if c.source is not Source.USER_DECLARED or c.billable:
        return False
    if c.category not in (Category.PERSONAL_TRANSFER, Category.OWN_TRANSFER):
        return False
    memo = (m.memo or "").lower()
    return m.amount >= t.risky_non_billable_amount or any(k in memo for k in INVOICE_MEMO_MARKERS)


def _variation_pct(current: Decimal, prior: Sequence[Decimal]) -> Decimal | None:
    base = [p for p in prior if p > 0]
    if len(base) < 3:
        return None
    avg = sum(base, Decimal("0")) / len(base)
    return (current - avg) / avg * 100
