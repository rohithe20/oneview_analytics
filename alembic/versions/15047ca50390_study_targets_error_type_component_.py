"""study targets, error type, component families

Revision ID: 15047ca50390
Revises: 811700661a43
Create Date: 2026-08-31 20:09:55.885259

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '15047ca50390'
down_revision: Union[str, Sequence[str], None] = '811700661a43'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
     # 1. component_families — maps a component number to Pure/Statistics.
    #    Reference data, seeded below. Keeping it as a table (not a CASE
    #    in a view) means the mapping lives in one place and is testable.
    op.create_table(
        "component_families",
        sa.Column("component", sa.Integer(), primary_key=True),
        sa.Column("family", sa.String(length=20), nullable=False),
    )
 
    # Seed the known 9709 mapping. CONFIRM these component numbers against
    # the actual papers your sister uses before trusting family metrics.
    # AS:  Paper 1 = Pure Maths 1 ; Paper 5 = Prob & Stats 1
    # A:   Paper 3 = Pure Maths 2 ; Paper 5 = Prob & Stats 2
    op.bulk_insert(
        sa.table(
            "component_families",
            sa.column("component", sa.Integer),
            sa.column("family", sa.String),
        ),
        [
            {"component": 1, "family": "Pure"},
            {"component": 3, "family": "Pure"},
            {"component": 5, "family": "Statistics"},
        ],
    )
 
    # 2. study_targets — one practice target per (student, level, family).
    op.create_table(
        "study_targets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "student_id",
            sa.Integer(),
            sa.ForeignKey("students.id"),
            nullable=False,
        ),
        sa.Column("exam_level", sa.String(length=2), nullable=False),
        sa.Column("component_family", sa.String(length=20), nullable=False),
        sa.Column("target_value", sa.Integer(), nullable=False),
        sa.UniqueConstraint(
            "student_id",
            "exam_level",
            "component_family",
            name="uq_study_targets_scope",
        ),
        sa.CheckConstraint("target_value >= 0", name="ck_study_targets_non_negative"),
    )
 
    # 3. error_type on sub_part_results — nine controlled values, nullable
    #    for now (existing rows and the seed path don't set it yet). The
    #    Record Practice Paper page enforces the allowed set and the
    #    "No Error when marks_lost = 0" rule in the service layer.
    op.add_column(
        "sub_part_results",
        sa.Column("error_type", sa.String(length=30), nullable=True),
    )
    


def downgrade() -> None:
   op.drop_column("sub_part_results", "error_type")
   op.drop_table("study_targets")
   op.drop_table("component_families")
