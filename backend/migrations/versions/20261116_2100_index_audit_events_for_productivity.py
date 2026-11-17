"""Index audit_events by action, period and entity (accountant productivity metrics).

Revision ID: 3c1f0a7d9e21
Revises: 6b28b9808564
Create Date: 2026-11-16 21:00:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "3c1f0a7d9e21"
down_revision: str | None = "6b28b9808564"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # On the partitioned parent: Postgres creates it on every partition, present and future.
    op.create_index(
        op.f("ix_audit_events_action_period_entity"),
        "audit_events",
        ["action", "period", "entity_id"],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_audit_events_action_period_entity"), table_name="audit_events")
