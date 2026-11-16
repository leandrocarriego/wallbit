"""Ports to ARCA and their mock implementations (ARCHITECTURE §10).

`InvoiceSource` reads a taxpayer's registration and issued invoices; `InvoiceIssuer` issues a
new one. The proposal swaps the mocks for AfipSDK-backed implementations; callers do not change.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Protocol

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.enums import Currency
from app.modules.arca.models import ArcaDocument, ArcaRegistration


@dataclass(frozen=True)
class IssueRequest:
    cuit: str
    customer_name: str
    customer_country: str | None
    description: str
    amount: Decimal
    currency: Currency
    fx_rate_ars: Decimal
    issued_on: date


class InvoiceSource(Protocol):
    def registration(self, cuit: str) -> ArcaRegistration | None: ...

    def documents(self, cuit: str) -> list[ArcaDocument]: ...


class InvoiceIssuer(Protocol):
    def issue(self, request: IssueRequest) -> ArcaDocument: ...


class MockArcaSource:
    def __init__(self, session: Session) -> None:
        self.session = session

    def registration(self, cuit: str) -> ArcaRegistration | None:
        query = select(ArcaRegistration).where(ArcaRegistration.cuit == cuit)
        return self.session.scalars(query).first()

    def documents(self, cuit: str) -> list[ArcaDocument]:
        query = (
            select(ArcaDocument)
            .where(ArcaDocument.cuit == cuit)
            .order_by(ArcaDocument.issued_on, ArcaDocument.number)
        )
        return list(self.session.scalars(query))


class MockArcaIssuer:
    """Issues invoices into the mock ARCA with the next number of point of sale 0001."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def issue(self, request: IssueRequest) -> ArcaDocument:
        count = self.session.scalar(
            select(func.count()).select_from(ArcaDocument).where(ArcaDocument.cuit == request.cuit)
        )
        last = self.session.scalar(
            select(func.max(ArcaDocument.number)).where(ArcaDocument.cuit == request.cuit)
        )
        next_number = int(last.split("-")[1]) + 1 if last else (count or 0) + 1
        document = ArcaDocument(
            cuit=request.cuit,
            number=f"E 0001-{next_number:08d}",
            issued_on=request.issued_on,
            customer_name=request.customer_name,
            customer_country=request.customer_country,
            description=request.description,
            amount=request.amount,
            currency=request.currency,
            fx_rate_ars=request.fx_rate_ars,
            issued_via_wallbit=True,
        )
        self.session.add(document)
        self.session.flush()
        return document
