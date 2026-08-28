from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, String, UniqueConstraint, func
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
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # NO unique constraint on (student_id, paper_id) — D5, papers may be re-attempted.

    student: Mapped[Student] = relationship(back_populates="attempts")
    paper: Mapped[Paper] = relationship()
    results: Mapped[list[SubPartResult]] = relationship(
        back_populates="attempt", cascade="all, delete-orphan"
    )


class SubPartResult(Base):
    __tablename__ = "sub_part_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    attempt_id: Mapped[int] = mapped_column(ForeignKey("attempts.id"), index=True)
    sub_part_id: Mapped[int] = mapped_column(ForeignKey("sub_parts.id"), index=True)
    marks_scored: Mapped[int]

    __table_args__ = (
        UniqueConstraint("attempt_id", "sub_part_id", name="result_identity"),
        CheckConstraint("marks_scored >= 0", name="marks_not_negative"),
    )

    attempt: Mapped[Attempt] = relationship(back_populates="results")
    sub_part: Mapped[SubPart] = relationship()
