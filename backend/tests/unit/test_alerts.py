"""Alerts and status for the two demo clients (pure domain, no DB)."""

from datetime import date
from decimal import Decimal

from app.core.enums import ActivityType, Currency, Direction, MonotributoCategory, MovementType
from app.modules.alerts.engine import (
    AlertInput,
    AlertType,
    CloseStatus,
    Severity,
    derive_status,
    evaluate_alerts,
)
from app.modules.classification.engine import (
    Category,
    Classification,
    ClassificationContext,
    Declaration,
    InvoiceIn,
    MovementIn,
    Source,
    classify_period,
    normalize_name,
)
from app.modules.tax_engine.engine import CloseInput, InvoiceAmount, compute_close
from seeds.params import PARAMS_2026_08


def mv(mid: str, amount: str, cp: str, day: int, **kw: object) -> MovementIn:
    return MovementIn(
        mid,
        MovementType.INCOMING_TRANSFER,
        Direction.IN,
        Decimal(amount),
        Currency.USD,
        date(2026, 10, day),
        normalize_name(cp),
        cp,
        **kw,
    )  # type: ignore[arg-type]


def martina(deadline_passed: bool) -> list:  # type: ignore[type-arg]
    invoices = [
        InvoiceIn("i41", "E-41", "acme corp", Decimal("1800"), Currency.USD, date(2026, 10, 2)),
        InvoiceIn(
            "i42", "E-42", "northwind ltd", Decimal("1200"), Currency.USD, date(2026, 10, 21)
        ),
    ]
    movements = [
        mv("m1", "1800", "Acme Corp", 2),
        mv("m2", "1200", "Acme Corp", 12),
        mv("m3", "300", "J. Pérez", 15, origin_country="AR"),
        mv("m4", "1200", "Northwind Ltd", 21),
    ]
    ctx = ClassificationContext(
        "Martina Ríos",
        invoices=invoices,
        declarations=[Declaration("d1", "acme corp", Category.SERVICE_INCOME)],
    )
    classes = classify_period(movements, ctx)
    result = compute_close(
        CloseInput(
            "2026-10",
            MonotributoCategory.D,
            ActivityType.SERVICES,
            [InvoiceAmount(i.number, i.amount, i.currency, Decimal("1450")) for i in invoices],
            Decimal("35450000"),
            PARAMS_2026_08,
        )
    )
    return evaluate_alerts(
        AlertInput(movements, classes, invoices, result, [Decimal("4300000")] * 3, deadline_passed)
    )


def test_martina_is_in_review_when_acme_collection_has_no_invoice() -> None:
    alerts = martina(deadline_passed=False)
    types = {a.type: a.severity for a in alerts}
    assert types[AlertType.UNBILLED_COLLECTION] is Severity.BLOCKING
    assert types[AlertType.UNCLASSIFIED] is Severity.WAITING  # J. Pérez: question for Martina
    assert types[AlertType.NEAR_CAP] is Severity.INFO
    assert derive_status(alerts, frozenset()) is CloseStatus.IN_REVIEW


def test_unclassified_blocks_when_answer_deadline_passed() -> None:
    alerts = martina(deadline_passed=True)
    unclassified = next(a for a in alerts if a.type is AlertType.UNCLASSIFIED)
    assert unclassified.severity is Severity.BLOCKING


def test_status_is_pending_when_only_user_questions_remain() -> None:
    alerts = martina(deadline_passed=False)
    resolved = frozenset(a.key for a in alerts if a.type is AlertType.UNBILLED_COLLECTION)
    assert derive_status(alerts, resolved) is CloseStatus.PENDING_DATA


def test_status_is_ready_when_every_blocking_alert_is_resolved() -> None:
    alerts = martina(deadline_passed=True)
    resolved = frozenset(a.key for a in alerts if a.severity is not Severity.INFO)
    assert derive_status(alerts, resolved) is CloseStatus.READY


def test_non_billable_declaration_is_flagged_when_amount_is_high() -> None:
    m = mv("m1", "4000", "A. Novak", 10)
    c = Classification("m1", Category.PERSONAL_TRANSFER, Source.USER_DECLARED, declaration_id="d9")
    result = compute_close(
        CloseInput(
            "2026-10",
            MonotributoCategory.D,
            ActivityType.SERVICES,
            [],
            Decimal("0"),
            PARAMS_2026_08,
        )
    )
    alerts = evaluate_alerts(AlertInput([m], [c], [], result, [], False))
    assert any(a.type is AlertType.NON_BILLABLE_RISK for a in alerts)


def test_strong_variation_when_invoiced_doubles_the_average() -> None:
    result = compute_close(
        CloseInput(
            "2026-10",
            MonotributoCategory.C,
            ActivityType.SERVICES,
            [InvoiceAmount("E-1", Decimal("4100"), Currency.USD, Decimal("1450"))],
            Decimal("0"),
            PARAMS_2026_08,
        )
    )
    alerts = evaluate_alerts(AlertInput([], [], [], result, [Decimal("3262500")] * 3, False))
    assert any(a.type is AlertType.STRONG_VARIATION for a in alerts)
