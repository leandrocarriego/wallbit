"""User-side use cases: enroll, link ARCA, answer "¿Quién es?" and invoice a payment."""

import uuid
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import DomainError, NotFoundError
from app.core.periods import period_of
from app.modules.arca.service import IssueRequest, MockArcaIssuer, MockArcaSource
from app.modules.audit.service import record
from app.modules.classification.engine import Category
from app.modules.classification.models import CounterpartyDeclaration
from app.modules.classification.service import reclassify
from app.modules.clients.models import Client
from app.modules.closing.service import mark_dirty
from app.modules.ingestion.models import Movement
from app.modules.invoices.models import Invoice
from app.modules.invoices.service import sync_from_arca
from app.modules.prompts.models import PromptKind, PromptStatus, UserPrompt

CURRENT_CONSENT_VERSION = "2026-11"
# Movements this far back are classified when ARCA gets linked.
BACKFILL_DAYS = 60
# What a user may answer to "¿Quién es?". "other" goes to the accountant as unclassified.
WHO_IS_ANSWERS = {
    "work": Category.SERVICE_INCOME,
    "own": Category.OWN_TRANSFER,
    "family": Category.PERSONAL_TRANSFER,
}


def get_client(session: Session, client_id: uuid.UUID) -> Client:
    client = session.get(Client, client_id)
    if client is None:
        raise NotFoundError("client_not_found", "No existe ese cliente.")
    return client


def enroll(
    session: Session,
    client: Client,
    *,
    consent_version: str,
    actor: str,
    now: datetime,
    today: date,
) -> Client:
    if consent_version != CURRENT_CONSENT_VERSION:
        raise DomainError("consent_outdated", "Hay una versión nueva del consentimiento.")
    if client.enrolled_at is not None:
        return client
    client.enrolled_at = now
    client.consent_version = consent_version
    client.service_since = today
    record(
        session,
        actor=actor,
        action="client.enrolled",
        entity_type="client",
        entity_id=client.id,
        client_id=client.id,
        after={"consent_version": consent_version},
    )
    return client


def link_arca(
    session: Session, client: Client, *, actor: str, now: datetime, today: date
) -> list[Invoice]:
    if client.enrolled_at is None:
        raise DomainError("not_enrolled", "Primero hay que adherir al servicio.")
    source = MockArcaSource(session)
    registration = source.registration(client.cuit)
    if registration is None:
        raise DomainError("arca_not_found", "ARCA no tiene registrado ese CUIT.")
    first_link = client.arca_linked_at is None
    client.category = registration.category
    client.activity_type = registration.activity_type
    client.arca_linked_at = client.arca_linked_at or now
    if first_link:
        record(
            session,
            actor=actor,
            action="client.arca_linked",
            entity_type="client",
            entity_id=client.id,
            client_id=client.id,
            after={"category": registration.category.value},
        )
    imported = sync_from_arca(session, client, source, actor=actor, now=now)
    # Continuous classification (decision 20): classify recent movements right away.
    since = period_of(today - timedelta(days=BACKFILL_DAYS))
    periods = sorted(
        set(
            session.scalars(
                select(Movement.period).where(
                    Movement.client_id == client.id, Movement.period >= since
                )
            )
        )
    )
    for period in periods:
        reclassify(session, client, period, actor=actor, now=now)
    return imported


def _open_prompt(
    session: Session, client: Client, prompt_id: uuid.UUID, kind: PromptKind
) -> UserPrompt:
    prompt = session.get(UserPrompt, prompt_id)
    if prompt is None or prompt.client_id != client.id or prompt.kind is not kind:
        raise NotFoundError("prompt_not_found", "No existe esa pregunta.")
    if prompt.status is not PromptStatus.OPEN:
        raise DomainError("prompt_closed", "Esa pregunta ya no está abierta.")
    return prompt


def answer_who_is(
    session: Session,
    client: Client,
    prompt_id: uuid.UUID,
    *,
    answer: str,
    actor: str,
    now: datetime,
) -> UserPrompt:
    prompt = _open_prompt(session, client, prompt_id, PromptKind.WHO_IS)
    movement = session.get(Movement, prompt.movement_id)
    assert movement is not None
    prompt.status = PromptStatus.ANSWERED
    prompt.closed_at = now
    prompt.payload = {**prompt.payload, "answer": answer}
    category = WHO_IS_ANSWERS.get(answer)
    if category is not None and movement.counterparty_id is not None:
        declaration = session.scalars(
            select(CounterpartyDeclaration).where(
                CounterpartyDeclaration.client_id == client.id,
                CounterpartyDeclaration.counterparty_id == movement.counterparty_id,
            )
        ).first() or CounterpartyDeclaration(
            client_id=client.id, counterparty_id=movement.counterparty_id
        )
        declaration.category = category
        declaration.declared_by = actor
        declaration.declared_at = now
        session.add(declaration)
    record(
        session,
        actor=actor,
        action="prompt.answered",
        entity_type="user_prompt",
        entity_id=prompt.id,
        client_id=client.id,
        period=prompt.period,
        after={"kind": prompt.kind.value, "answer": answer},
    )
    session.flush()
    reclassify(session, client, prompt.period, actor=actor, now=now)
    mark_dirty(session, client.id, prompt.period)
    return prompt


def invoice_movement(
    session: Session,
    client: Client,
    movement_id: uuid.UUID,
    *,
    description: str,
    actor: str,
    now: datetime,
    today: date,
) -> Invoice:
    """ "Facturar este cobro": issue the invoice in ARCA (mock), import it and reclassify."""
    if not client.is_active:
        raise DomainError("not_active", "Hay que adherir y vincular ARCA para facturar.")
    movement = session.get(Movement, movement_id)
    if movement is None or movement.client_id != client.id:
        raise NotFoundError("movement_not_found", "No existe ese cobro.")
    prompt = session.scalars(
        select(UserPrompt).where(
            UserPrompt.movement_id == movement.id,
            UserPrompt.kind == PromptKind.INVOICE_THIS,
            UserPrompt.status == PromptStatus.OPEN,
        )
    ).first()
    if prompt is None:
        raise DomainError("nothing_to_invoice", "Este cobro no necesita factura.")

    issuer = MockArcaIssuer(session)
    document = issuer.issue(
        IssueRequest(
            cuit=client.cuit,
            customer_name=str(prompt.payload["counterparty"]),
            customer_country=movement.origin_country,
            description=description,
            amount=movement.amount,
            currency=movement.currency,
            fx_rate_ars=movement.fx_rate_ars,
            issued_on=today,
        )
    )
    record(
        session,
        actor=actor,
        action="invoice.issued_in_arca",
        entity_type="movement",
        entity_id=movement.id,
        client_id=client.id,
        period=movement.period,
        after={"number": document.number, "amount": str(document.amount)},
    )
    prompt.status = PromptStatus.ANSWERED
    prompt.closed_at = now
    imported = sync_from_arca(session, client, MockArcaSource(session), actor=actor, now=now)
    invoice = next(i for i in imported if i.arca_document_id == document.id)
    invoice.issued_for_movement_id = movement.id
    session.flush()
    reclassify(session, client, movement.period, actor=actor, now=now)
    mark_dirty(session, client.id, movement.period)
    return invoice
