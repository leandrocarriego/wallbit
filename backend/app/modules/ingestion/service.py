from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.classification.engine import normalize_name
from app.modules.ingestion.models import Counterparty


def counterparty_for(
    session: Session, raw_name: str | None, country: str | None = None
) -> Counterparty | None:
    """Return the single entity behind a raw name, creating it the first time we see it."""
    if not raw_name:
        return None
    key = normalize_name(raw_name)
    found = session.scalars(select(Counterparty).where(Counterparty.normalized_name == key)).first()
    if found is not None:
        return found
    created = Counterparty(normalized_name=key, display_name=raw_name.strip(), country=country)
    session.add(created)
    session.flush()
    return created
