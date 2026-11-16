"""FICTITIOUS tax parameters for the prototype (valid from 2026-08). Not real figures."""

from decimal import Decimal

from app.core.enums import MonotributoCategory as Cat
from app.modules.tax_engine.engine import CategoryParams, TaxParams

_ROWS = [
    # category, annual cap ARS, services fee, goods fee
    (Cat.A, "9000000", "25000", "24000"),
    (Cat.B, "15100000", "33200", "31500"),
    (Cat.C, "21200000", "41900", "39800"),
    (Cat.D, "47400000", "58300", "55100"),
    (Cat.E, "55800000", "79600", "75200"),
    (Cat.F, "70000000", "98000", "92500"),
    (Cat.G, "84000000", "120000", "113000"),
    (Cat.H, "127000000", "160000", "151000"),
    (Cat.I, "142000000", "210000", "198000"),
    (Cat.J, "163000000", "250000", "236000"),
    (Cat.K, "195000000", "300000", "283000"),
]

PARAMS_2026_08 = TaxParams(
    name="2026-08",
    categories=tuple(
        CategoryParams(cat, Decimal(cap), Decimal(fee_s), Decimal(fee_g))
        for cat, cap, fee_s, fee_g in _ROWS
    ),
    regime_max_annual_ars=Decimal("195000000"),
    fee_due_day=20,
)
