"""Registry of every ORM model: Alembic and tests import this module."""

from app.modules.arca.models import ArcaDocument, ArcaRegistration
from app.modules.audit.models import AuditEvent
from app.modules.classification.models import (
    CounterpartyDeclaration,
    GlobalRuleRow,
    MovementClassification,
)
from app.modules.clients.models import Client
from app.modules.closing.models import CloseAlert, PeriodClose
from app.modules.demo.models import DemoClock
from app.modules.ingestion.models import Counterparty, Movement
from app.modules.invoices.models import Invoice
from app.modules.parameters.models import MonotributoCategoryParam, TaxParameterSet
from app.modules.prompts.models import UserPrompt

__all__ = [
    "ArcaDocument",
    "ArcaRegistration",
    "AuditEvent",
    "Client",
    "CloseAlert",
    "Counterparty",
    "CounterpartyDeclaration",
    "DemoClock",
    "GlobalRuleRow",
    "Invoice",
    "MonotributoCategoryParam",
    "Movement",
    "MovementClassification",
    "PeriodClose",
    "TaxParameterSet",
    "UserPrompt",
]
