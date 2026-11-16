"""Monotributo tax engine (v1). Pure and versioned: every result carries its trace.

Figures (caps, fees, regime maximum) arrive as versioned parameters from the DB;
no tax number is hardcoded here.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from app.core.enums import ActivityType, Currency, MonotributoCategory

ENGINE_VERSION = "0.1.0"
ACTIVITY_LABEL = {ActivityType.SERVICES: "servicios", ActivityType.GOODS: "bienes"}
CENT = Decimal("0.01")


def money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class CategoryParams:
    category: MonotributoCategory
    annual_cap_ars: Decimal
    monthly_fee_services_ars: Decimal
    monthly_fee_goods_ars: Decimal


@dataclass(frozen=True)
class TaxParams:
    name: str
    categories: Sequence[CategoryParams]
    regime_max_annual_ars: Decimal
    fee_due_day: int = 20

    def cap_of(self, category: MonotributoCategory) -> CategoryParams:
        return next(c for c in self.categories if c.category is category)


@dataclass(frozen=True)
class InvoiceAmount:
    number: str
    amount: Decimal
    currency: Currency
    fx_rate_ars: Decimal


@dataclass(frozen=True)
class TraceLine:
    label: str
    value: str


@dataclass(frozen=True)
class CloseInput:
    period: str
    category: MonotributoCategory
    activity_type: ActivityType
    invoices: Sequence[InvoiceAmount]
    prior_11_months_ars: Decimal  # invoiced in the previous 11 months (approved snapshots)
    params: TaxParams


@dataclass(frozen=True)
class CloseResult:
    period: str
    invoiced_by_currency: dict[str, Decimal]
    invoiced_ars: Decimal
    rolling_12m_ars: Decimal
    category: MonotributoCategory
    category_cap_ars: Decimal
    cap_usage_pct: Decimal
    required_category: MonotributoCategory | None  # None: above the regime maximum
    exceeds_category: bool
    exceeds_regime: bool
    monthly_fee_ars: Decimal
    due_date: date
    engine_version: str
    params_name: str
    trace: tuple[TraceLine, ...]


def compute_close(data: CloseInput) -> CloseResult:
    trace: list[TraceLine] = []
    params = data.params

    by_currency: dict[str, Decimal] = {}
    invoiced_ars = Decimal("0")
    for inv in data.invoices:
        by_currency[inv.currency.value] = by_currency.get(inv.currency.value, Decimal("0")) + (
            inv.amount
        )
        invoiced_ars += money(inv.amount * inv.fx_rate_ars)
    numbers = " + ".join(i.number for i in data.invoices) or "sin facturas"
    trace.append(TraceLine(f"Facturas del período: {numbers}", _fmt_currencies(by_currency)))
    trace.append(TraceLine("En pesos, con el tipo de cambio de cada factura", _ars(invoiced_ars)))

    rolling = money(data.prior_11_months_ars + invoiced_ars)
    trace.append(
        TraceLine(
            f"Acumulado 12 meses: {_ars(data.prior_11_months_ars)} + {_ars(invoiced_ars)}",
            _ars(rolling),
        )
    )

    current = params.cap_of(data.category)
    usage = (rolling / current.annual_cap_ars * 100).quantize(Decimal("0.1"), ROUND_HALF_UP)
    trace.append(
        TraceLine(
            f"Tope categoría {data.category} (parámetros {params.name})",
            f"{_ars(current.annual_cap_ars)} → {usage}%",
        )
    )

    exceeds_regime = rolling > params.regime_max_annual_ars
    required = None
    if not exceeds_regime:
        fitting = sorted(
            (c for c in params.categories if c.annual_cap_ars >= rolling),
            key=lambda c: c.annual_cap_ars,
        )
        required = fitting[0].category if fitting else None
        exceeds_regime = required is None
    exceeds_category = rolling > current.annual_cap_ars
    if exceeds_regime:
        trace.append(TraceLine("Supera el máximo del régimen", _ars(params.regime_max_annual_ars)))
    elif exceeds_category:
        trace.append(TraceLine("Supera su categoría: corresponde", str(required)))

    fee = (
        current.monthly_fee_services_ars
        if data.activity_type is ActivityType.SERVICES
        else current.monthly_fee_goods_ars
    )
    due = _due_date(data.period, params.fee_due_day)
    trace.append(
        TraceLine(
            f"Cuota categoría {data.category}, {ACTIVITY_LABEL[data.activity_type]}",
            f"{_ars(fee)} · vence {due:%d/%m}",
        )
    )

    return CloseResult(
        period=data.period,
        invoiced_by_currency=by_currency,
        invoiced_ars=money(invoiced_ars),
        rolling_12m_ars=rolling,
        category=data.category,
        category_cap_ars=current.annual_cap_ars,
        cap_usage_pct=usage,
        required_category=required,
        exceeds_category=exceeds_category,
        exceeds_regime=exceeds_regime,
        monthly_fee_ars=fee,
        due_date=due,
        engine_version=ENGINE_VERSION,
        params_name=params.name,
        trace=tuple(trace),
    )


def _due_date(period: str, day: int) -> date:
    year, month = (int(x) for x in period.split("-"))
    year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return date(year, month, day)


def _ars(value: Decimal) -> str:
    return f"$ {money(value):,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


def _num(value: Decimal) -> str:
    return f"{money(value):,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


def _fmt_currencies(values: dict[str, Decimal]) -> str:
    return " · ".join(f"{cur} {_num(v)}" for cur, v in sorted(values.items())) or "0"
