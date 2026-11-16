import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel

from app.core.enums import Currency, MonotributoCategory
from app.modules.invoices.models import InvoiceSource
from app.modules.prompts.models import PromptKind


class ClientSummary(BaseModel):
    id: uuid.UUID
    full_name: str
    cuit: str
    activity: str
    category: MonotributoCategory | None
    enrolled: bool
    arca_linked: bool


class PromptOut(BaseModel):
    id: uuid.UUID
    kind: PromptKind
    movement_id: uuid.UUID
    period: str
    payload: dict[str, Any]


class Home(BaseModel):
    client: ClientSummary
    stage: Literal["offer", "link_arca", "active"]
    consent_version: str
    prompts: list[PromptOut]


class EnrollmentIn(BaseModel):
    consent_version: str
    accepted: bool


class InvoiceOut(BaseModel):
    id: uuid.UUID
    number: str
    issued_on: date
    customer_name: str
    amount: Decimal
    currency: Currency
    source: InvoiceSource
    received_at: datetime


class ArcaLinkOut(BaseModel):
    client: ClientSummary
    imported: list[InvoiceOut]
    prompts: list[PromptOut]


class WhoIsAnswer(BaseModel):
    answer: Literal["work", "own", "family", "other"]


class InvoiceThisIn(BaseModel):
    description: str = "Servicios profesionales"
