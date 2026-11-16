"""Tax engine golden cases: if the calculation changes, these fail and require review."""

from datetime import date
from decimal import Decimal

import pytest

from app.core.enums import ActivityType, Currency
from app.core.enums import MonotributoCategory as Cat
from app.modules.tax_engine.engine import CloseInput, InvoiceAmount, compute_close
from seeds.params import PARAMS_2026_08


def inv(number: str, amount: str, fx: str = "1450") -> InvoiceAmount:
    return InvoiceAmount(number, Decimal(amount), Currency.USD, Decimal(fx))


def close(
    category: Cat,
    invoices: list[InvoiceAmount],
    prior: str,
    activity: ActivityType = ActivityType.SERVICES,
) -> CloseInput:
    return CloseInput("2026-10", category, activity, invoices, Decimal(prior), PARAMS_2026_08)


GOLDEN = [
    # id, category, invoices, prior 11 months, expected: ars, rolling, %, required, fee
    (
        "martina_d_84pct",
        Cat.D,
        [inv("E-41", "1800"), inv("E-42", "1200")],
        "35450000",
        "4350000.00",
        "39800000.00",
        "84.0",
        Cat.D,
        "58300",
    ),
    (
        "mateo_d_58pct",
        Cat.D,
        [inv("E-17", "2100"), inv("E-18", "1100")],
        "22852000",
        "4640000.00",
        "27492000.00",
        "58.0",
        Cat.D,
        "58300",
    ),
    (
        "supera_categoria",
        Cat.C,
        [inv("E-9", "2000")],
        "19000000",
        "2900000.00",
        "21900000.00",
        "103.3",
        Cat.D,
        "41900",
    ),
    ("sin_facturas", Cat.B, [], "6000000", "0.00", "6000000.00", "39.7", Cat.A, "33200"),
]


@pytest.mark.parametrize(
    ("case", "category", "invoices", "prior", "ars", "rolling", "pct", "required", "fee"),
    GOLDEN,
    ids=[g[0] for g in GOLDEN],
)
def test_golden_case(
    case: str,
    category: Cat,
    invoices: list[InvoiceAmount],
    prior: str,
    ars: str,
    rolling: str,
    pct: str,
    required: Cat,
    fee: str,
) -> None:
    r = compute_close(close(category, invoices, prior))
    assert r.invoiced_ars == Decimal(ars)
    assert r.rolling_12m_ars == Decimal(rolling)
    assert r.cap_usage_pct == Decimal(pct)
    assert r.required_category is required
    assert r.monthly_fee_ars == Decimal(fee)
    assert r.due_date == date(2026, 11, 20)


def test_exceeds_regime_when_rolling_is_above_maximum() -> None:
    r = compute_close(close(Cat.K, [inv("E-1", "10000")], "190000000"))
    assert r.exceeds_regime and r.required_category is None


def test_each_invoice_uses_its_own_exchange_rate() -> None:
    r = compute_close(close(Cat.D, [inv("E-1", "100", "1400"), inv("E-2", "100", "1500.5")], "0"))
    assert r.invoiced_ars == Decimal("290050.00")


def test_goods_activity_uses_goods_fee() -> None:
    r = compute_close(close(Cat.D, [], "0", activity=ActivityType.GOODS))
    assert r.monthly_fee_ars == Decimal("55100")


def test_due_date_rolls_to_january_when_period_is_december() -> None:
    data = CloseInput("2026-12", Cat.D, ActivityType.SERVICES, [], Decimal("0"), PARAMS_2026_08)
    assert compute_close(data).due_date == date(2027, 1, 20)


def test_result_is_explainable_and_versioned() -> None:
    r = compute_close(close(Cat.D, [inv("E-41", "1800")], "0"))
    assert r.engine_version and r.params_name == "2026-08"
    assert len(r.trace) >= 4
