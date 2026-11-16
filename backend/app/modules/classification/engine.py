"""Layered movement classification (ARCHITECTURE §4). Pure function: no I/O, no clock.

Layers, the first one that decides wins:
  1. structural (movement type)          4. user declaration per counterparty
  2. global rules (by priority)          5. suggestion (suggests only, never classifies)
  3. ARCA invoice match (or invoice        6. unclassified → question to the user
     history with that counterparty)
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import StrEnum
from statistics import mean, pstdev

from app.core.enums import Currency, Direction, MovementType


class Category(StrEnum):
    SERVICE_INCOME = "service_income"
    PLATFORM_WITHDRAWAL = "platform_withdrawal"
    OWN_TRANSFER = "own_transfer"
    CONVERSION = "conversion"
    REFUND_REVERSAL = "refund_reversal"
    INVESTMENT_INCOME = "investment_income"
    PERSONAL_TRANSFER = "personal_transfer"
    CARD_EXPENSE = "card_expense"
    OUTGOING_PAYMENT = "outgoing_payment"
    UNCLASSIFIED = "unclassified"


BILLABLE = frozenset({Category.SERVICE_INCOME, Category.PLATFORM_WITHDRAWAL})


class Source(StrEnum):
    STRUCTURAL = "structural"
    GLOBAL_RULE = "global_rule"
    INVOICE_MATCH = "invoice_match"
    INVOICE_HISTORY = "invoice_history"
    USER_DECLARED = "user_declared"
    ACCOUNTANT = "accountant"
    NONE = "none"


@dataclass(frozen=True)
class MovementIn:
    id: str
    type: MovementType
    direction: Direction
    amount: Decimal
    currency: Currency
    occurred_on: date
    counterparty_key: str | None = None
    counterparty_name: str | None = None
    origin_holder_name: str | None = None
    origin_provider: str | None = None
    origin_country: str | None = None
    memo: str | None = None


@dataclass(frozen=True)
class RuleCondition:
    """Every condition that is set must hold."""

    movement_type: MovementType | None = None
    counterparty_contains: tuple[str, ...] = ()
    origin_provider_in: tuple[str, ...] = ()
    holder_is_client: bool | None = None


@dataclass(frozen=True)
class GlobalRule:
    id: str
    priority: int
    condition: RuleCondition
    category: Category
    description: str


@dataclass(frozen=True)
class InvoiceIn:
    id: str
    number: str
    counterparty_key: str | None
    amount: Decimal
    currency: Currency
    issued_on: date
    # Set when the invoice was issued from Wallbit for a specific payment ("Facturar este cobro").
    for_movement_id: str | None = None


@dataclass(frozen=True)
class Declaration:
    id: str
    counterparty_key: str
    category: Category


@dataclass(frozen=True)
class PriorPayment:
    """Payment from the same counterparty in previous months (feeds the suggestion)."""

    counterparty_key: str
    period: str
    amount: Decimal


@dataclass(frozen=True)
class Suggestion:
    category: Category
    score: float
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class TraceStep:
    layer: str
    outcome: str


@dataclass(frozen=True)
class Classification:
    movement_id: str
    category: Category
    source: Source
    rule_id: str | None = None
    invoice_id: str | None = None
    declaration_id: str | None = None
    suggestion: Suggestion | None = None
    trace: tuple[TraceStep, ...] = field(default_factory=tuple)

    @property
    def billable(self) -> bool:
        return self.category in BILLABLE

    @property
    def needs_answer(self) -> bool:
        return self.category is Category.UNCLASSIFIED


@dataclass(frozen=True)
class ClassificationContext:
    client_full_name: str
    rules: Sequence[GlobalRule] = ()
    invoices: Sequence[InvoiceIn] = ()
    declarations: Sequence[Declaration] = ()
    history: Sequence[PriorPayment] = ()
    # Counterparties this client has invoiced before in ARCA: evidence of a work relationship.
    invoiced_counterparties: frozenset[str] = frozenset()
    # Invoice match tolerances: platforms deduct fees.
    match_tolerance: Decimal = Decimal("0.05")
    match_days_before: int = 45
    match_days_after: int = 30


STRUCTURAL: dict[MovementType, Category] = {
    MovementType.CONVERSION: Category.CONVERSION,
    MovementType.CARD_PAYMENT: Category.CARD_EXPENSE,
    MovementType.YIELD_CREDIT: Category.INVESTMENT_INCOME,
    MovementType.INTERNAL_TRANSFER: Category.OWN_TRANSFER,
    MovementType.REFUND: Category.REFUND_REVERSAL,
}

COMPANY_MARKERS = ("inc", "llc", "ltd", "corp", "gmbh", "s.a", "srl", "co.", "limited", "bv")
INVOICE_MEMO_MARKERS = (
    "invoice",
    "inv-",
    "inv ",
    "factura",
    "services",
    "consulting",
    "contractor",
)


def normalize_name(name: str) -> str:
    """'ACME CORP.' and 'Acme Corp' → 'acme corp'."""
    cleaned = "".join(ch if ch.isalnum() or ch.isspace() else " " for ch in name.lower())
    return " ".join(cleaned.split())


def classify_period(
    movements: Iterable[MovementIn], ctx: ClassificationContext
) -> list[Classification]:
    """Classify one client's movements for a period. Each invoice matches a single payment."""
    used_invoices: set[str] = set()
    ordered = sorted(movements, key=lambda m: (m.occurred_on, m.id))
    return [_classify(m, ctx, used_invoices) for m in ordered]


def _classify(m: MovementIn, ctx: ClassificationContext, used: set[str]) -> Classification:
    trace: list[TraceStep] = []

    # 1. Structural
    if m.type in STRUCTURAL:
        cat = STRUCTURAL[m.type]
        trace.append(TraceStep("estructural", f"{m.type.value} → {cat.value}"))
        return Classification(m.id, cat, Source.STRUCTURAL, trace=tuple(trace))
    if m.direction is Direction.OUT:
        cat = Category.OWN_TRANSFER if _holder_is_client(m, ctx) else Category.OUTGOING_PAYMENT
        trace.append(TraceStep("estructural", f"salida → {cat.value}"))
        return Classification(m.id, cat, Source.STRUCTURAL, trace=tuple(trace))
    trace.append(TraceStep("estructural", "transferencia entrante: no decide"))

    # 2. Global rules
    for rule in sorted(ctx.rules, key=lambda r: r.priority):
        if _rule_matches(rule.condition, m, ctx):
            trace.append(TraceStep("regla global", f"{rule.description} → {rule.category.value}"))
            return Classification(
                m.id, rule.category, Source.GLOBAL_RULE, rule_id=rule.id, trace=tuple(trace)
            )
    trace.append(TraceStep("regla global", "ninguna aplica"))

    # 3. Invoice match
    invoice = _match_invoice(m, ctx, used)
    if invoice is not None:
        used.add(invoice.id)
        trace.append(TraceStep("factura", f"matchea {invoice.number} ({invoice.amount})"))
        return Classification(
            m.id,
            Category.SERVICE_INCOME,
            Source.INVOICE_MATCH,
            invoice_id=invoice.id,
            trace=tuple(trace),
        )
    trace.append(TraceStep("factura", "sin factura que coincida"))
    if m.counterparty_key and m.counterparty_key in ctx.invoiced_counterparties:
        trace.append(TraceStep("historial ARCA", "ya le facturó antes a esta contraparte"))
        return Classification(
            m.id, Category.SERVICE_INCOME, Source.INVOICE_HISTORY, trace=tuple(trace)
        )

    # 4. User declaration
    declaration = next(
        (d for d in ctx.declarations if m.counterparty_key == d.counterparty_key), None
    )
    if declaration is not None:
        trace.append(TraceStep("declaración", f"el usuario la declaró {declaration.category}"))
        return Classification(
            m.id,
            declaration.category,
            Source.USER_DECLARED,
            declaration_id=declaration.id,
            trace=tuple(trace),
        )
    trace.append(TraceStep("declaración", "contraparte sin declarar"))

    # 5. Suggestion (does not classify) and 6. unclassified
    suggestion = suggest(m, ctx.history)
    trace.append(
        TraceStep(
            "sugerencia",
            f"{suggestion.category.value} ({suggestion.score:.2f})" if suggestion else "ninguna",
        )
    )
    return Classification(
        m.id, Category.UNCLASSIFIED, Source.NONE, suggestion=suggestion, trace=tuple(trace)
    )


def _holder_is_client(m: MovementIn, ctx: ClassificationContext) -> bool:
    name = m.origin_holder_name or m.counterparty_name
    return bool(name) and normalize_name(name or "") == normalize_name(ctx.client_full_name)


def _rule_matches(c: RuleCondition, m: MovementIn, ctx: ClassificationContext) -> bool:
    if c.movement_type is not None and m.type is not c.movement_type:
        return False
    if c.counterparty_contains:
        key = m.counterparty_key or ""
        if not any(token in key for token in c.counterparty_contains):
            return False
    if c.origin_provider_in and (m.origin_provider or "").lower() not in c.origin_provider_in:
        return False
    return not (c.holder_is_client is not None and _holder_is_client(m, ctx) != c.holder_is_client)


def _match_invoice(m: MovementIn, ctx: ClassificationContext, used: set[str]) -> InvoiceIn | None:
    explicit = next(
        (i for i in ctx.invoices if i.for_movement_id == m.id and i.id not in used), None
    )
    if explicit is not None:
        return explicit
    candidates = []
    for inv in ctx.invoices:
        if inv.id in used or inv.currency != m.currency or inv.for_movement_id:
            continue
        if not m.counterparty_key or inv.counterparty_key != m.counterparty_key:
            continue
        delta_days = (m.occurred_on - inv.issued_on).days
        if not -ctx.match_days_after <= delta_days <= ctx.match_days_before:
            continue
        # The payment may be lower than the invoice because of fees, never higher.
        if not inv.amount * (1 - ctx.match_tolerance) <= m.amount <= inv.amount:
            continue
        candidates.append(inv)
    # Prefer the closest amount and, on ties, the oldest invoice.
    candidates.sort(key=lambda i: (abs(i.amount - m.amount), i.issued_on, i.id))
    return candidates[0] if candidates else None


def suggest(m: MovementIn, history: Sequence[PriorPayment]) -> Suggestion | None:
    """Deterministic heuristic. A local ML model can later implement the same contract."""
    reasons: list[str] = []
    memo = (m.memo or "").lower()
    if any(marker in memo for marker in INVOICE_MEMO_MARKERS):
        return Suggestion(Category.SERVICE_INCOME, 0.8, ("el memo menciona factura o servicios",))

    prior = [p for p in history if p.counterparty_key == m.counterparty_key]
    months = {p.period for p in prior}
    if len(months) >= 3:
        amounts = [float(p.amount) for p in prior] + [float(m.amount)]
        stable = pstdev(amounts) / mean(amounts) < 0.15
        if stable:
            return Suggestion(
                Category.SERVICE_INCOME,
                0.7,
                (f"paga todos los meses desde hace {len(months)} meses", "monto estable"),
            )
        reasons.append(f"{len(months) + 1} transferencias con montos distintos")

    name = normalize_name(m.counterparty_name or m.counterparty_key or "")
    looks_like_person = bool(name) and not any(mk in f" {name} " for mk in COMPANY_MARKERS)
    if looks_like_person and m.origin_country in (None, "AR") and not memo:
        reasons = ["nombre de persona, no de empresa", "sin referencia de factura", *reasons]
        return Suggestion(Category.PERSONAL_TRANSFER, 0.6, tuple(reasons))
    return None
