"""analytics views with scope

Revision ID: 811700661a43
Revises: 6723188cc924
Create Date: 2026-08-27 20:26:58.693629

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "811700661a43"
down_revision: str | Sequence[str] | None = "6723188cc924"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        CREATE VIEW v_attempt_totals AS
        SELECT
            a.id                              AS attempt_id,
            a.student_id,
            a.paper_id,
            p.level                           AS exam_level,
            CASE
                WHEN p.component IN (1, 3) THEN 'Pure'
                WHEN p.component IN (5, 6) THEN 'Statistics'
                ELSE 'Other'
            END                               AS component_family,
            a.completed_at,
            COALESCE(SUM(r.marks_scored), 0)  AS marks_scored,
            COALESCE(SUM(sp.max_marks), 0)    AS marks_available,
            ROUND(
                100.0 * COALESCE(SUM(r.marks_scored), 0)
                / NULLIF(SUM(sp.max_marks), 0), 2
            )                                 AS percentage,
            COUNT(DISTINCT q.id)              AS questions_attempted
        FROM attempts a
        JOIN papers p           ON p.id = a.paper_id
        JOIN sub_part_results r ON r.attempt_id = a.id
        JOIN sub_parts sp       ON sp.id = r.sub_part_id
        JOIN questions q        ON q.id = sp.question_id
        WHERE a.status = 'COMPLETED'
        GROUP BY a.id, a.student_id, a.paper_id, p.level, p.component, a.completed_at
    """)

    op.execute("""
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
    """)


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS v_topic_performance")
    op.execute("DROP VIEW IF EXISTS v_attempt_totals")
