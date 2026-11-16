from datetime import date
from decimal import Decimal

from app.core.enums import Currency, Direction, MovementType
from app.modules.classification.engine import (
    Category,
    ClassificationContext,
    Declaration,
    GlobalRule,
    InvoiceIn,
    MovementIn,
    PriorPayment,
    RuleCondition,
    Source,
    classify_period,
    normalize_name,
)

CLIENT = "Martina Ríos"


def incoming(
    mid: str, amount: str, cp: str, on: date = date(2026, 10, 12), **kw: object
) -> MovementIn:
    return MovementIn(
        id=mid,
        type=MovementType.INCOMING_TRANSFER,
        direction=Direction.IN,
        amount=Decimal(amount),
        currency=Currency.USD,
        occurred_on=on,
        counterparty_key=normalize_name(cp),
        counterparty_name=cp,
        **kw,  # type: ignore[arg-type]
    )


def invoice(iid: str, amount: str, cp: str, on: date) -> InvoiceIn:
    return InvoiceIn(iid, f"E 0001-{iid}", normalize_name(cp), Decimal(amount), Currency.USD, on)


def one(movement: MovementIn, ctx: ClassificationContext) -> object:
    return classify_period([movement], ctx)[0]


def test_conversion_is_structural_when_type_is_conversion() -> None:
    m = MovementIn(
        "m1",
        MovementType.CONVERSION,
        Direction.OUT,
        Decimal("500"),
        Currency.USD,
        date(2026, 10, 5),
    )
    c = classify_period([m], ClassificationContext(CLIENT))[0]
    assert (c.category, c.source) == (Category.CONVERSION, Source.STRUCTURAL)


def test_outgoing_to_own_account_is_own_transfer_when_holder_is_client() -> None:
    m = MovementIn(
        "m1",
        MovementType.OUTGOING_TRANSFER,
        Direction.OUT,
        Decimal("2000"),
        Currency.USD,
        date(2026, 10, 24),
        counterparty_name="MARTINA RIOS",
    )
    c = classify_period([m], ClassificationContext("Martina Rios"))[0]
    assert c.category is Category.OWN_TRANSFER


def test_global_rule_wins_over_invoice_when_both_apply() -> None:
    rule = GlobalRule(
        "r1",
        10,
        RuleCondition(counterparty_contains=("upwork",)),
        Category.SERVICE_INCOME,
        "plataforma conocida",
    )
    m = incoming("m1", "300", "Upwork Global Inc")
    c = classify_period([m], ClassificationContext(CLIENT, rules=[rule]))[0]
    assert (c.source, c.rule_id) == (Source.GLOBAL_RULE, "r1")


def test_platform_withdrawal_when_holder_is_client_and_provider_is_payoneer() -> None:
    rule = GlobalRule(
        "r2",
        20,
        RuleCondition(origin_provider_in=("payoneer", "paypal", "wise"), holder_is_client=True),
        Category.PLATFORM_WITHDRAWAL,
        "retiro de plataforma propia",
    )
    m = incoming(
        "m1", "900", "Martina Rios", origin_holder_name="Martina Rios", origin_provider="payoneer"
    )
    c = classify_period([m], ClassificationContext("Martina Rios", rules=[rule]))[0]
    assert c.category is Category.PLATFORM_WITHDRAWAL and c.billable


def test_invoice_match_tolerates_platform_fee_when_collected_less() -> None:
    ctx = ClassificationContext(
        CLIENT, invoices=[invoice("41", "1000", "Acme Corp", date(2026, 10, 1))]
    )
    c = classify_period([incoming("m1", "970", "ACME CORP.")], ctx)[0]
    assert (c.category, c.source, c.invoice_id) == (
        Category.SERVICE_INCOME,
        Source.INVOICE_MATCH,
        "41",
    )


def test_invoice_does_not_match_when_collected_more_than_invoiced() -> None:
    ctx = ClassificationContext(
        CLIENT, invoices=[invoice("41", "1000", "Acme Corp", date(2026, 10, 1))]
    )
    c = classify_period([incoming("m1", "1100", "Acme Corp")], ctx)[0]
    assert c.invoice_id is None


def test_invoice_matches_previous_month_when_within_window() -> None:
    ctx = ClassificationContext(
        CLIENT, invoices=[invoice("40", "1800", "Acme Corp", date(2026, 9, 28))]
    )
    c = classify_period([incoming("m1", "1800", "Acme Corp", on=date(2026, 10, 2))], ctx)[0]
    assert c.invoice_id == "40"


def test_one_invoice_matches_only_one_collection_when_two_are_equal() -> None:
    ctx = ClassificationContext(
        CLIENT, invoices=[invoice("41", "1200", "Acme Corp", date(2026, 10, 1))]
    )
    first, second = classify_period(
        [
            incoming("m1", "1200", "Acme Corp", on=date(2026, 10, 2)),
            incoming("m2", "1200", "Acme Corp", on=date(2026, 10, 12)),
        ],
        ctx,
    )
    assert first.invoice_id == "41" and second.invoice_id is None


def test_declared_counterparty_classifies_when_no_invoice_matches() -> None:
    ctx = ClassificationContext(
        CLIENT, declarations=[Declaration("d1", "acme corp", Category.SERVICE_INCOME)]
    )
    c = classify_period([incoming("m1", "1200", "Acme Corp")], ctx)[0]
    assert (c.source, c.declaration_id, c.billable) == (Source.USER_DECLARED, "d1", True)


def test_unknown_person_is_unclassified_with_personal_suggestion() -> None:
    history = [
        PriorPayment("j perez", "2026-06", Decimal("120")),
        PriorPayment("j perez", "2026-08", Decimal("450")),
    ]
    m = incoming("m1", "300", "J. Pérez", on=date(2026, 10, 15), origin_country="AR")
    c = classify_period([m], ClassificationContext(CLIENT, history=history))[0]
    assert c.category is Category.UNCLASSIFIED and c.needs_answer
    assert c.suggestion is not None and c.suggestion.category is Category.PERSONAL_TRANSFER


def test_memo_with_invoice_suggests_service_income() -> None:
    m = incoming("m1", "2300", "Hooli GmbH", memo="Invoice 0042")
    c = classify_period([m], ClassificationContext(CLIENT))[0]
    assert c.suggestion is not None and c.suggestion.category is Category.SERVICE_INCOME


def test_every_classification_carries_a_trace() -> None:
    c = classify_period([incoming("m1", "10", "Nadie SRL")], ClassificationContext(CLIENT))[0]
    assert [step.layer for step in c.trace] == [
        "estructural",
        "regla global",
        "factura",
        "declaración",
        "sugerencia",
    ]


def test_unbilled_payment_is_billable_when_client_invoiced_that_counterparty_before() -> None:
    ctx = ClassificationContext(CLIENT, invoiced_counterparties=frozenset({"acme corp"}))
    c = classify_period([incoming("m1", "1200", "Acme Corp")], ctx)[0]
    assert (c.category, c.source, c.invoice_id) == (
        Category.SERVICE_INCOME,
        Source.INVOICE_HISTORY,
        None,
    )


def test_invoice_issued_for_a_payment_matches_it_even_weeks_later() -> None:
    late = InvoiceIn(
        "43",
        "E-43",
        "acme corp",
        Decimal("1200"),
        Currency.USD,
        date(2026, 11, 20),
        for_movement_id="m1",
    )
    c = classify_period(
        [incoming("m1", "1200", "Acme Corp")], ClassificationContext(CLIENT, invoices=[late])
    )[0]
    assert c.invoice_id == "43"


def test_invoice_issued_for_another_payment_is_not_reused() -> None:
    other = InvoiceIn(
        "43",
        "E-43",
        "acme corp",
        Decimal("1200"),
        Currency.USD,
        date(2026, 10, 12),
        for_movement_id="m9",
    )
    c = classify_period(
        [incoming("m1", "1200", "Acme Corp")], ClassificationContext(CLIENT, invoices=[other])
    )[0]
    assert c.invoice_id is None
