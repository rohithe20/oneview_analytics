from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.enums import AttemptStatus
from app.models.reference import Paper, SubPart


class Student(Base):
    __tablename__ = "students"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True)
    display_name: Mapped[str] = mapped_column(String(100))
    level: Mapped[str] = mapped_column(String(2), default="AS")
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    attempts: Mapped[list[Attempt]] = relationship(back_populates="student")


class Attempt(Base):
    __tablename__ = "attempts"

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), index=True)
    paper_id: Mapped[int] = mapped_column(ForeignKey("papers.id"), index=True)
    status: Mapped[AttemptStatus] = mapped_column(
        Enum(AttemptStatus, name="attempt_status"), default=AttemptStatus.DRAFT
    )
    notes: Mapped[str | None] = mapped_column(String(300))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # The BRD's "Date Completed" (record-service.md) — the exam date the student
    # states on the form. Distinct from completed_at, which is the timestamp the
    # analytics views order by; app/services/record.py writes both. Migration
    # 7c4c306f3eca.
    date_completed: Mapped[date | None] = mapped_column(Date())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # NO unique constraint on (student_id, paper_id) — D5, papers may be re-attempted.

    student: Mapped[Student] = relationship(back_populates="attempts")
    paper: Mapped[Paper] = relationship()
    results: Mapped[list[SubPartResult]] = relationship(
        back_populates="attempt", cascade="all, delete-orphan"
    )


class StudyTarget(Base):
    """One practice target per (student, exam_level, component_family).

    Not keyed by subject — the subject is always Maths (9709); the
    independence is per component family (docs/specs/planning-performance.md).
    Table and constraints already exist in migration 15047ca50390; this maps
    them, it does not redefine them.
    """

    __tablename__ = "study_targets"

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"))
    exam_level: Mapped[str] = mapped_column(String(2))
    component_family: Mapped[str] = mapped_column(String(20))
    target_value: Mapped[int]

    __table_args__ = (
        UniqueConstraint(
            "student_id", "exam_level", "component_family", name="uq_study_targets_scope"
        ),
        # Named to match the constraint the migration actually created — the
        # metadata naming convention prefixes 'ck_study_targets_' to whatever
        # name it is given, so the DB name is doubled. Do not "tidy" this.
        CheckConstraint("target_value >= 0", name="ck_study_targets_non_negative"),
    )

    student: Mapped[Student] = relationship()


class SubPartResult(Base):
    __tablename__ = "sub_part_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    attempt_id: Mapped[int] = mapped_column(ForeignKey("attempts.id"), index=True)
    sub_part_id: Mapped[int] = mapped_column(ForeignKey("sub_parts.id"), index=True)
    marks_scored: Mapped[int]
    # One of the nine controlled values in app/services/record.py ERROR_TYPES.
    # Nullable: the seed/demo path and pre-existing rows never set it. Column
    # created by migration 15047ca50390 — mapping it here needs no migration.
    error_type: Mapped[str | None] = mapped_column(String(30))

    __table_args__ = (
        UniqueConstraint("attempt_id", "sub_part_id", name="result_identity"),
        CheckConstraint("marks_scored >= 0", name="marks_not_negative"),
    )

    attempt: Mapped[Attempt] = relationship(back_populates="results")
    sub_part: Mapped[SubPart] = relationship()
