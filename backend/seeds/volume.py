"""Volume seed for load tests: N clients already enrolled and linked to (mock) ARCA.

Not the demo seed: this one exists to measure the day-1 burst and the console under load.
Usage: python -m seeds.volume --clients 2000

Mix of cases (deterministic, seeded RNG):
  ~70% clean (every payment invoiced), ~15% one payment without invoice from a known client,
  ~10% a transfer from an unknown person, ~5% near the category cap.
"""

import argparse
import random
import time
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import insert
from sqlalchemy.orm import Session

from app.core.db import SessionLocal
from app.core.enums import ActivityType, Currency, Direction, MonotributoCategory, MovementType
from app.core.periods import AR, period_of, shift
from app.modules.arca.models import ArcaDocument, ArcaRegistration
from app.modules.classification.engine import normalize_name
from app.modules.clients.models import Client
from app.modules.demo.models import DemoClock
from app.modules.ingestion.models import Counterparty, Movement
from app.modules.invoices.models import Invoice, InvoiceSource
from seeds import run

FX = Decimal("1450.000000")
PERIOD = "2026-10"
COMPANIES = [
    "Acme Corp", "Globex Inc", "Initech LLC", "Umbrella Ltd", "Hooli GmbH", "Stark Industries",
    "Wayne Enterprises", "Soylent Corp", "Tyrell Corp", "Cyberdyne Systems", "Vandelay Industries",
    "Massive Dynamic", "Northwind Ltd", "Contoso Ltd", "Fabrikam Inc", "Pied Piper Inc",
]  # fmt: skip
PEOPLE = ["L. Torres", "K. Smith", "R. Gómez", "A. Novak", "J. Pérez", "M. Silva"]
CATEGORIES = [MonotributoCategory.C, MonotributoCategory.D, MonotributoCategory.E]
CAPS = {
    MonotributoCategory.C: 21_200_000,
    MonotributoCategory.D: 47_400_000,
    MonotributoCategory.E: 55_800_000,
}


def at(day: date) -> datetime:
    return datetime(day.year, day.month, day.day, 15, tzinfo=AR).astimezone(UTC)


def seed_volume(session: Session, clients: int, rng: random.Random) -> dict[str, int]:
    now = datetime.now(UTC)
    counterparties = {}
    for name in COMPANIES + PEOPLE:
        cp = Counterparty(id=uuid.uuid4(), normalized_name=normalize_name(name), display_name=name)
        counterparties[name] = cp
    session.add_all(counterparties.values())
    session.flush()

    rows: dict[str, list[dict[str, object]]] = {
        "clients": [], "registrations": [], "documents": [], "invoices": [], "movements": []
    }  # fmt: skip
    cases = {"clean": 0, "unbilled": 0, "unknown": 0, "near_cap": 0}
    for i in range(clients):
        cid = uuid.uuid4()
        cuit = f"20-{50_000_000 + i:08d}-{i % 10}"
        category = rng.choice(CATEGORIES)
        roll = rng.random()
        case = (
            "clean"
            if roll < 0.70
            else "unbilled"
            if roll < 0.85
            else "unknown"
            if roll < 0.95
            else "near_cap"
        )
        cases[case] += 1
        rows["clients"].append(
            {"id": cid, "full_name": f"Cliente {i:04d}", "cuit": cuit, "activity": "Servicios al exterior",
             "regime": "monotributo", "category": category, "activity_type": ActivityType.SERVICES,
             "jurisdiction": "CABA", "service_since": date(2026, 1, 1), "enrolled_at": now,
             "consent_version": "2026-11", "arca_linked_at": now}
        )  # fmt: skip
        rows["registrations"].append(
            {
                "id": uuid.uuid4(),
                "cuit": cuit,
                "category": category,
                "activity_type": ActivityType.SERVICES,
            }
        )
        customer = rng.choice(COMPANIES)
        cap_share = 0.9 if case == "near_cap" else rng.uniform(0.3, 0.7)
        monthly = Decimal(int(CAPS[category] * cap_share / 12 / float(FX)))
        n = 1
        for m in range(11, 0, -1):  # 11 previous months, for the 12-month total
            n = _invoice(
                rows,
                cid,
                cuit,
                n,
                date.fromisoformat(f"{shift(PERIOD, -m)}-05"),
                counterparties[customer],
                monthly,
                now,
            )
        # October: two payments from the customer, both invoiced unless the case says otherwise.
        first, second = (
            (monthly * Decimal("0.6")).quantize(Decimal("1")),
            (monthly * Decimal("0.4")).quantize(Decimal("1")),
        )
        for day, amount, invoiced in (
            (date(2026, 10, 3), first, True),
            (date(2026, 10, 18), second, case != "unbilled"),
        ):
            if invoiced:
                n = _invoice(rows, cid, cuit, n, day, counterparties[customer], amount, now)
            _movement(
                rows,
                cid,
                day,
                MovementType.INCOMING_TRANSFER,
                Direction.IN,
                amount,
                counterparties[customer],
            )
        if case == "unknown":
            person = rng.choice(PEOPLE)
            _movement(rows, cid, date(2026, 10, 22), MovementType.INCOMING_TRANSFER, Direction.IN,
                      Decimal(rng.randint(100, 600)), counterparties[person], country="AR")  # fmt: skip
        _movement(
            rows,
            cid,
            date(2026, 10, 9),
            MovementType.CARD_PAYMENT,
            Direction.OUT,
            Decimal("35"),
            None,
        )
        _movement(
            rows,
            cid,
            date(2026, 10, 12),
            MovementType.CONVERSION,
            Direction.OUT,
            Decimal("300"),
            None,
        )

    for model, key in ((Client, "clients"), (ArcaRegistration, "registrations"), (ArcaDocument, "documents"),
                       (Invoice, "invoices"), (Movement, "movements")):  # fmt: skip
        for start in range(0, len(rows[key]), 5_000):
            session.execute(insert(model), rows[key][start : start + 5_000])
    return {**cases, "movements": len(rows["movements"]), "invoices": len(rows["invoices"])}


def _invoice(
    rows: dict[str, list[dict[str, object]]], cid: uuid.UUID, cuit: str, n: int, day: date,
    customer: Counterparty, amount: Decimal, now: datetime,
) -> int:  # fmt: skip
    doc_id = uuid.uuid4()
    number = f"E 0001-{n:08d}"
    rows["documents"].append(
        {"id": doc_id, "cuit": cuit, "number": number, "issued_on": day, "customer_name": customer.display_name,
         "customer_country": "US", "description": "Servicios", "amount": amount, "currency": Currency.USD,
         "fx_rate_ars": FX, "issued_via_wallbit": False}
    )  # fmt: skip
    rows["invoices"].append(
        {"id": uuid.uuid4(), "client_id": cid, "arca_document_id": doc_id, "number": number, "issued_on": day,
         "period": period_of(day), "counterparty_id": customer.id, "customer_name": customer.display_name, "amount": amount,
         "currency": Currency.USD, "fx_rate_ars": FX, "source": InvoiceSource.ARCA_IMPORTED, "received_at": now}
    )  # fmt: skip
    return n + 1


def _movement(
    rows: dict[str, list[dict[str, object]]], cid: uuid.UUID, day: date, mtype: MovementType,
    direction: Direction, amount: Decimal, cp: Counterparty | None, country: str = "US",
) -> None:  # fmt: skip
    occurred = at(day)
    rows["movements"].append(
        {"id": uuid.uuid4(), "client_id": cid, "external_id": f"vol-{uuid.uuid4().hex[:20]}",
         "occurred_at": occurred, "period": period_of(occurred), "type": mtype, "direction": direction,
         "amount": amount, "currency": Currency.USD, "fx_rate_ars": FX,
         "counterparty_id": cp.id if cp else None, "counterparty_raw": cp.display_name if cp else None,
         "origin_country": country if cp else None}
    )  # fmt: skip


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clients", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    started = time.perf_counter()
    with SessionLocal() as session, session.begin():
        run.reset(session)
        run.seed_parameters(session)
        run.seed_rules(session)
        run.seed_templates(session)
        session.add(DemoClock(id=1, today=date(2026, 10, 31)))
        stats = seed_volume(session, args.clients, random.Random(args.seed))
    elapsed = time.perf_counter() - started
    print(f"Volumen listo en {elapsed:.1f} s: {args.clients} clientes activos · {stats}")


if __name__ == "__main__":
    main()
