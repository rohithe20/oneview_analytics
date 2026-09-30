"""attempts date_completed

Revision ID: 7c4c306f3eca
Revises: 7f3c9d2b41ae
Create Date: 2026-09-27 00:00:00.000000

The BRD's "Date Completed" field (Record Practice Paper §7) is a DATE the
student types on the form. `attempts.completed_at` already exists, but it is
a timestamptz written by the seed/demo path and — more importantly — it is
what every analytics view orders by (`v_latest_paper_attempts`,
`v_attempt_totals`). The two are not interchangeable: one is the student's
stated exam date, the other is the ordering key analytics already depend on.

So this adds the BRD field rather than repurposing `completed_at`, and
`app/services/record.py` writes BOTH from the same input — otherwise an
attempt recorded through the write path would carry a NULL `completed_at`
and sort last in `ORDER BY completed_at DESC NULLS LAST`, silently ranking
the newest attempt as the oldest.

Nullable: existing rows (demo/seed attempts) have no stated exam date, and
inventing one from `completed_at` would fabricate data the student never
entered.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7c4c306f3eca"
down_revision: str | Sequence[str] | None = "7f3c9d2b41ae"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("attempts", sa.Column("date_completed", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("attempts", "date_completed")
