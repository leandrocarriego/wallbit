from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.periods import period_of
from app.modules.arca.service import InvoiceSource
from app.modules.audit.service import record
from app.modules.clients.models import Client
from app.modules.ingestion.service import counterparty_for
from app.modules.invoices.models import Invoice
from app.modules.invoices.models import InvoiceSource as Origin


def sync_from_arca(
    session: Session, client: Client, source: InvoiceSource, *, actor: str, now: datetime
) -> list[Invoice]:
    """Copy into `invoices` every ARCA document of the client we do not have yet. Idempotent."""
    known = set(
        session.scalars(select(Invoice.arca_document_id).where(Invoice.client_id == client.id))
    )
    created: list[Invoice] = []
    for doc in source.documents(client.cuit):
        if doc.id in known:
            continue
        counterparty = counterparty_for(session, doc.customer_name, doc.customer_country)
        invoice = Invoice(
            client_id=client.id,
            arca_document_id=doc.id,
            number=doc.number,
            issued_on=doc.issued_on,
            period=period_of(doc.issued_on),
            counterparty_id=counterparty.id if counterparty else None,
            customer_name=doc.customer_name,
            amount=doc.amount,
            currency=doc.currency,
            fx_rate_ars=doc.fx_rate_ars,
            source=Origin.ARCA_ISSUED if doc.issued_via_wallbit else Origin.ARCA_IMPORTED,
            received_at=now,
        )
        session.add(invoice)
        created.append(invoice)
    session.flush()
    if created:
        record(
            session,
            actor=actor,
            action="invoices.synced_from_arca",
            entity_type="client",
            entity_id=client.id,
            client_id=client.id,
            after={"invoices": [i.number for i in created]},
        )
    return created
