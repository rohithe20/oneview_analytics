"""latest attempt per paper

Only the most recent completed attempt at a given paper counts towards any
metric (PO decision 2026-09-05, docs/specs/planning-performance.md). This
migration puts that rule in ONE place — the v_latest_paper_attempts view —
and re-points v_topic_performance at it so every topic/subtopic aggregate
inherits it. v_attempt_totals is deliberately left alone: it stays the raw
per-attempt fact view, and readers join v_latest_paper_attempts to reduce it.

Revision ID: 7f3c9d2b41ae
Revises: 15047ca50390
Create Date: 2026-09-05 00:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7f3c9d2b41ae"
down_revision: str | Sequence[str] | None = "15047ca50390"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


TOPIC_PERFORMANCE_WITHOUT_REDUCTION = """
    CREATE VIEW v_topic_performance AS
    SELECT
        a.student_id,
        p.level                           AS exam_level,
        CASE
            WHEN p.component IN (1, 3) THEN 'Pure'
            WHEN p.component IN (5, 6) THEN 'Statistics'
            ELSE 'Other'
        END                               AS component_family,
        t.id                              AS topic_id,
        t.name                            AS topic_name,
        t.sort_order,
        SUM(r.marks_scored)               AS marks_scored,
        SUM(sp.max_marks)                 AS marks_available,
        SUM(sp.max_marks - r.marks_scored) AS marks_lost,
        ROUND(
            100.0 * SUM(r.marks_scored)
            / NULLIF(SUM(sp.max_marks), 0), 2
        )                                 AS percentage,
        COUNT(DISTINCT a.id)              AS attempts_count
    FROM attempts a
    JOIN papers p           ON p.id = a.paper_id
    JOIN sub_part_results r ON r.attempt_id = a.id
    JOIN sub_parts sp       ON sp.id = r.sub_part_id
    JOIN topics t           ON t.id = sp.topic_id
    WHERE a.status = 'COMPLETED'
    GROUP BY a.student_id, p.level, p.component, t.id, t.name, t.sort_order
"""

TOPIC_PERFORMANCE_LATEST_PER_PAPER = """
    CREATE VIEW v_topic_performance AS
    SELECT
        a.student_id,
        p.level                           AS exam_level,
        CASE
            WHEN p.component IN (1, 3) THEN 'Pure'
            WHEN p.component IN (5, 6) THEN 'Statistics'
            ELSE 'Other'
        END                               AS component_family,
        t.id                              AS topic_id,
        t.name                            AS topic_name,
        t.sort_order,
        SUM(r.marks_scored)               AS marks_scored,
        SUM(sp.max_marks)                 AS marks_available,
        SUM(sp.max_marks - r.marks_scored) AS marks_lost,
        ROUND(
            100.0 * SUM(r.marks_scored)
            / NULLIF(SUM(sp.max_marks), 0), 2
        )                                 AS percentage,
        COUNT(DISTINCT a.id)              AS attempts_count
    FROM attempts a
    JOIN v_latest_paper_attempts la ON la.attempt_id = a.id
    JOIN papers p           ON p.id = a.paper_id
    JOIN sub_part_results r ON r.attempt_id = a.id
    JOIN sub_parts sp       ON sp.id = r.sub_part_id
    JOIN topics t           ON t.id = sp.topic_id
    WHERE a.status = 'COMPLETED'
    GROUP BY a.student_id, p.level, p.component, t.id, t.name, t.sort_order
"""


def upgrade() -> None:
    # The single definition of "the attempt that counts" for a paper. A paper
    # may be attempted many times (data-model.md); the newest completed attempt
    # supersedes the rest, so re-marking or re-sitting replaces a result rather
    # than adding a second observation. Ties on completed_at break on id, so the
    # choice is deterministic.
    op.execute("""
        CREATE VIEW v_latest_paper_attempts AS
        SELECT DISTINCT ON (a.student_id, a.paper_id)
            a.id           AS attempt_id,
            a.student_id   AS student_id,
            a.paper_id     AS paper_id,
            a.completed_at AS completed_at
        FROM attempts a
        WHERE a.status = 'COMPLETED'
        ORDER BY a.student_id, a.paper_id, a.completed_at DESC NULLS LAST, a.id DESC
    """)

    op.execute("DROP VIEW IF EXISTS v_topic_performance")
    op.execute(TOPIC_PERFORMANCE_LATEST_PER_PAPER)


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS v_topic_performance")
    op.execute(TOPIC_PERFORMANCE_WITHOUT_REDUCTION)
    op.execute("DROP VIEW IF EXISTS v_latest_paper_attempts")
