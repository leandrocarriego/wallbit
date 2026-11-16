"""User-facing endpoints (the app simulator in the web calls these as `client:<id>`)."""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import DomainError
from app.core.http import Actor, DbSession
from app.modules.clients.models import Client
from app.modules.demo.service import today
from app.modules.enrollment import service
from app.modules.enrollment.schemas import (
    ArcaLinkOut,
    ClientSummary,
    EnrollmentIn,
    Home,
    InvoiceOut,
    InvoiceThisIn,
    PromptOut,
    WhoIsAnswer,
)
from app.modules.invoices.models import Invoice
from app.modules.prompts.models import PromptStatus, UserPrompt

router = APIRouter(prefix="/api/v1/clients", tags=["user"])


def _summary(c: Client) -> ClientSummary:
    return ClientSummary(
        id=c.id,
        full_name=c.full_name,
        cuit=c.cuit,
        activity=c.activity,
        category=c.category,
        enrolled=c.enrolled_at is not None,
        arca_linked=c.arca_linked_at is not None,
    )


def _open_prompts(session: Session, client: Client) -> list[PromptOut]:
    prompts = session.scalars(
        select(UserPrompt)
        .where(UserPrompt.client_id == client.id, UserPrompt.status == PromptStatus.OPEN)
        .order_by(UserPrompt.created_at)
    )
    return [
        PromptOut(
            id=p.id, kind=p.kind, movement_id=p.movement_id, period=p.period, payload=p.payload
        )
        for p in prompts
    ]


def _invoice_out(i: Invoice) -> InvoiceOut:
    return InvoiceOut(
        id=i.id,
        number=i.number,
        issued_on=i.issued_on,
        customer_name=i.customer_name,
        amount=i.amount,
        currency=i.currency,
        source=i.source,
        received_at=i.received_at,
    )


@router.get("")
def list_clients(session: DbSession) -> list[ClientSummary]:
    return [_summary(c) for c in session.scalars(select(Client).order_by(Client.full_name))]


@router.get("/{client_id}/home")
def home(client_id: uuid.UUID, session: DbSession) -> Home:
    client = service.get_client(session, client_id)
    stage = (
        "offer"
        if client.enrolled_at is None
        else "link_arca"
        if client.arca_linked_at is None
        else "active"
    )
    return Home(
        client=_summary(client),
        stage=stage,
        consent_version=service.CURRENT_CONSENT_VERSION,
        prompts=_open_prompts(session, client),
    )


@router.post("/{client_id}/enrollment")
def enroll(
    client_id: uuid.UUID, body: EnrollmentIn, session: DbSession, actor: Actor
) -> ClientSummary:
    if not body.accepted:
        raise DomainError("consent_required", "Sin consentimiento no podemos ofrecer el servicio.")
    client = service.get_client(session, client_id)
    service.enroll(
        session,
        client,
        consent_version=body.consent_version,
        actor=actor,
        now=datetime.now(UTC),
        today=today(session),
    )
    return _summary(client)


@router.post("/{client_id}/arca-link")
def link_arca(client_id: uuid.UUID, session: DbSession, actor: Actor) -> ArcaLinkOut:
    client = service.get_client(session, client_id)
    imported = service.link_arca(
        session, client, actor=actor, now=datetime.now(UTC), today=today(session)
    )
    return ArcaLinkOut(
        client=_summary(client),
        imported=[_invoice_out(i) for i in imported],
        prompts=_open_prompts(session, client),
    )


@router.get("/{client_id}/prompts")
def prompts(client_id: uuid.UUID, session: DbSession) -> list[PromptOut]:
    return _open_prompts(session, service.get_client(session, client_id))


@router.post("/{client_id}/prompts/{prompt_id}/answer")
def answer(
    client_id: uuid.UUID, prompt_id: uuid.UUID, body: WhoIsAnswer, session: DbSession, actor: Actor
) -> list[PromptOut]:
    client = service.get_client(session, client_id)
    service.answer_who_is(
        session, client, prompt_id, answer=body.answer, actor=actor, now=datetime.now(UTC)
    )
    return _open_prompts(session, client)


@router.post("/{client_id}/movements/{movement_id}/invoice")
def invoice_this(
    client_id: uuid.UUID,
    movement_id: uuid.UUID,
    body: InvoiceThisIn,
    session: DbSession,
    actor: Actor,
) -> InvoiceOut:
    client = service.get_client(session, client_id)
    invoice = service.invoice_movement(
        session,
        client,
        movement_id,
        description=body.description,
        actor=actor,
        now=datetime.now(UTC),
        today=today(session),
    )
    return _invoice_out(invoice)
