"""Demo seed: two Wallbit users not enrolled yet, their October 2026 movements and their
invoices in the mock ARCA. Run with `make seed` (wipes the demo data first).
"""

from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.db import SessionLocal
from app.core.enums import ActivityType, Currency, Direction, MonotributoCategory, MovementType
from app.core.periods import AR, period_of, shift
from app.modules.arca.models import ArcaDocument, ArcaRegistration
from app.modules.classification.engine import Category
from app.modules.classification.models import GlobalRuleRow
from app.modules.clients.models import Client
from app.modules.demo.models import DemoClock
from app.modules.ingestion.models import Movement
from app.modules.ingestion.service import counterparty_for
from app.modules.notifications.models import NotificationTemplate
from app.modules.parameters.models import MonotributoCategoryParam, TaxParameterSet
from seeds.params import PARAMS_2026_08

FX = Decimal("1450.000000")
DEMO_TODAY = date(2026, 10, 31)

TABLES = [
    "notifications",
    "close_snapshots",
    "batch_approvals",
    "alert_messages",
    "close_alerts",
    "period_closes",
    "movement_overrides",
    "notification_templates",
    "user_prompts",
    "movement_classifications",
    "counterparty_declarations",
    "global_rules",
    "invoices",
    "movements",
    "counterparties",
    "arca_documents",
    "arca_registrations",
    "clients",
    "monotributo_categories",
    "tax_parameter_sets",
    "demo_clock",
    "audit_events",
]


def reset(session: Session) -> None:
    session.flush()  # raw SQL does not autoflush: pending rows would survive the wipe
    # TRUNCATE skips the row-level append-only trigger on audit_events: demo reset only.
    session.execute(text(f"TRUNCATE {', '.join(TABLES)} RESTART IDENTITY CASCADE"))


def seed_parameters(session: Session) -> None:
    params = TaxParameterSet(
        name=PARAMS_2026_08.name,
        valid_from=date(2026, 8, 1),
        regime_max_annual_ars=PARAMS_2026_08.regime_max_annual_ars,
        notes="Valores FICTICIOS del prototipo.",
        created_by="seed",
    )
    session.add(params)
    session.flush()
    for c in PARAMS_2026_08.categories:
        session.add(
            MonotributoCategoryParam(
                parameter_set_id=params.id,
                category=c.category,
                annual_cap_ars=c.annual_cap_ars,
                monthly_fee_services_ars=c.monthly_fee_services_ars,
                monthly_fee_goods_ars=c.monthly_fee_goods_ars,
            )
        )


def seed_rules(session: Session) -> None:
    rules = [
        (
            10,
            "Plataforma de trabajo conocida",
            {"counterparty_contains": ["deel", "upwork", "toptal", "remote com"]},
            Category.SERVICE_INCOME,
        ),
        (
            20,
            "Retiro desde plataforma de cobro propia",
            {"origin_provider_in": ["payoneer", "paypal", "wise"], "holder_is_client": True},
            Category.PLATFORM_WITHDRAWAL,
        ),
        (
            30,
            "Transferencia desde una cuenta propia",
            {"holder_is_client": True},
            Category.OWN_TRANSFER,
        ),
    ]
    for priority, description, condition, category in rules:
        session.add(
            GlobalRuleRow(
                priority=priority,
                description=description,
                condition=condition,
                category=category,
                created_by="seed",
            )
        )


def at(day: date, hour: int = 15) -> datetime:
    return datetime(day.year, day.month, day.day, hour, tzinfo=AR).astimezone(UTC)


def add_movement(
    session: Session,
    client: Client,
    ext: str,
    day: date,
    mtype: MovementType,
    direction: Direction,
    amount: str,
    counterparty: str | None = None,
    **extra: str,
) -> None:
    cp = counterparty_for(session, counterparty, extra.get("origin_country"))
    occurred = at(day)
    session.add(
        Movement(
            client_id=client.id,
            external_id=ext,
            occurred_at=occurred,
            period=period_of(occurred),
            type=mtype,
            direction=direction,
            amount=Decimal(amount),
            currency=Currency.USD,
            fx_rate_ars=FX,
            counterparty_id=cp.id if cp else None,
            counterparty_raw=counterparty,
            **extra,
        )
    )


def add_document(
    session: Session, cuit: str, n: int, day: date, customer: str, amount: str, country: str
) -> None:
    session.add(
        ArcaDocument(
            cuit=cuit,
            number=f"E 0001-{n:08d}",
            issued_on=day,
            customer_name=customer,
            customer_country=country,
            description="Servicios profesionales",
            amount=Decimal(amount),
            currency=Currency.USD,
            fx_rate_ars=FX,
        )
    )


def prior_months(period: str, count: int) -> list[date]:
    return [date.fromisoformat(f"{shift(period, -i)}-05") for i in range(count, 0, -1)]


def seed_martina(session: Session) -> None:
    cuit = "27-30000012-4"
    client = Client(
        full_name="Martina Ríos",
        cuit=cuit,
        activity="Diseño UX para clientes del exterior",
        jurisdiction="CABA",
    )
    session.add(client)
    session.add(
        ArcaRegistration(
            cuit=cuit, category=MonotributoCategory.D, activity_type=ActivityType.SERVICES
        )
    )
    session.flush()

    # 11 previous months invoiced to Acme (rolling 12 months ≈ 83% of category D).
    n = 30
    for day in prior_months("2026-10", 11):
        add_document(session, cuit, n, day, "Acme Corp", "2200", "US")
        n += 1
    # October: Acme 02/10 and Northwind 21/10 are invoiced; Acme 12/10 is NOT (the demo case).
    add_document(session, cuit, 41, date(2026, 10, 2), "Acme Corp", "1800", "US")
    add_document(session, cuit, 42, date(2026, 10, 21), "Northwind Ltd", "1200", "GB")

    # History for the suggestion: J. Pérez sent varying amounts before.
    add_movement(
        session,
        client,
        "wb-mr-0601",
        date(2026, 6, 10),
        MovementType.INCOMING_TRANSFER,
        Direction.IN,
        "120",
        "J. Pérez",
        origin_country="AR",
    )
    add_movement(
        session,
        client,
        "wb-mr-0812",
        date(2026, 8, 12),
        MovementType.INCOMING_TRANSFER,
        Direction.IN,
        "450",
        "J. Pérez",
        origin_country="AR",
    )

    add_movement(
        session,
        client,
        "wb-mr-1002",
        date(2026, 10, 2),
        MovementType.INCOMING_TRANSFER,
        Direction.IN,
        "1800",
        "ACME CORP",
        origin_country="US",
        memo="Payment INV-0041",
    )
    add_movement(
        session,
        client,
        "wb-mr-1005",
        date(2026, 10, 5),
        MovementType.CONVERSION,
        Direction.OUT,
        "500",
    )
    add_movement(
        session,
        client,
        "wb-mr-1009",
        date(2026, 10, 9),
        MovementType.CARD_PAYMENT,
        Direction.OUT,
        "12",
        "Spotify",
    )
    add_movement(
        session,
        client,
        "wb-mr-1012",
        date(2026, 10, 12),
        MovementType.INCOMING_TRANSFER,
        Direction.IN,
        "1200",
        "Acme Corp.",
        origin_country="US",
    )
    add_movement(
        session,
        client,
        "wb-mr-1015",
        date(2026, 10, 15),
        MovementType.INCOMING_TRANSFER,
        Direction.IN,
        "300",
        "J. Pérez",
        origin_country="AR",
    )
    add_movement(
        session,
        client,
        "wb-mr-1021",
        date(2026, 10, 21),
        MovementType.INCOMING_TRANSFER,
        Direction.IN,
        "1200",
        "Northwind Ltd",
        origin_country="GB",
    )
    add_movement(
        session,
        client,
        "wb-mr-1024",
        date(2026, 10, 24),
        MovementType.OUTGOING_TRANSFER,
        Direction.OUT,
        "2000",
        "Martina Ríos",
        origin_provider="banco galicia",
    )
    add_movement(
        session,
        client,
        "wb-mr-1030",
        date(2026, 10, 30),
        MovementType.CARD_PAYMENT,
        Direction.OUT,
        "85",
        "Supermercado Día",
    )


def seed_mateo(session: Session) -> None:
    cuit = "20-40000002-3"
    client = Client(
        full_name="Mateo Giménez",
        cuit=cuit,
        activity="Desarrollo de software",
        jurisdiction="Córdoba",
    )
    session.add(client)
    session.add(
        ArcaRegistration(
            cuit=cuit, category=MonotributoCategory.D, activity_type=ActivityType.SERVICES
        )
    )
    session.flush()

    # Steady client: the last 3 months are close to October, so no "strong variation" alert.
    n = 5
    for i, day in enumerate(prior_months("2026-10", 11)):
        add_document(session, cuit, n, day, "Globex Inc", "3100" if i >= 8 else "1450", "US")
        n += 1
    add_document(session, cuit, 17, date(2026, 10, 3), "Globex Inc", "2100", "US")
    add_document(session, cuit, 18, date(2026, 10, 18), "Globex Inc", "1100", "US")

    add_movement(
        session,
        client,
        "wb-mg-1003",
        date(2026, 10, 3),
        MovementType.INCOMING_TRANSFER,
        Direction.IN,
        "2100",
        "GLOBEX INC",
        origin_country="US",
    )
    add_movement(
        session,
        client,
        "wb-mg-1008",
        date(2026, 10, 8),
        MovementType.CONVERSION,
        Direction.OUT,
        "1000",
    )
    add_movement(
        session,
        client,
        "wb-mg-1018",
        date(2026, 10, 18),
        MovementType.INCOMING_TRANSFER,
        Direction.IN,
        "1100",
        "Globex Inc",
        origin_country="US",
    )
    add_movement(
        session,
        client,
        "wb-mg-1022",
        date(2026, 10, 22),
        MovementType.CARD_PAYMENT,
        Direction.OUT,
        "40",
        "Mercado Libre",
    )
    add_movement(
        session,
        client,
        "wb-mg-1029",
        date(2026, 10, 29),
        MovementType.YIELD_CREDIT,
        Direction.IN,
        "6.20",
        "Wallbit",
    )


CLOSE_TEMPLATE = (
    "Hola {nombre}, tu contador revisó tu cierre de {mes}.\n"
    "Facturaste {facturado_usd} ({facturado_ars}).\n"
    "Tenés que pagar {cuota} de monotributo antes del {vencimiento}."
)


def seed_templates(session: Session) -> None:
    session.add(
        NotificationTemplate(
            name="close_approved",
            version=1,
            body=CLOSE_TEMPLATE,
            approved_by="C.P. Laura Gómez (ficticia)",
            approved_at=datetime(2026, 8, 1, tzinfo=UTC),
        )
    )


def seed_demo(session: Session) -> None:
    """Wipe everything and load the demo from scratch. Shared by `make seed` and the console."""
    reset(session)
    seed_parameters(session)
    seed_rules(session)
    seed_templates(session)
    seed_martina(session)
    seed_mateo(session)
    session.add(DemoClock(id=1, today=DEMO_TODAY))


def run() -> None:
    with SessionLocal() as session, session.begin():
        seed_demo(session)
    print(f"Seed listo: 2 usuarios sin adherir, fecha simulada {DEMO_TODAY:%d/%m/%Y}.")


if __name__ == "__main__":
    run()
