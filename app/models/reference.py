from __future__ import annotations

from sqlalchemy import CheckConstraint, Enum, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.enums import ExamSession


class Subject(Base):
    __tablename__ = "subjects"

    id: Mapped[int] = mapped_column(primary_key=True)
    board: Mapped[str] = mapped_column(String(50))
    code: Mapped[str] = mapped_column(String(10))
    name: Mapped[str] = mapped_column(String(100))

    __table_args__ = (UniqueConstraint("board", "code", name="subject_identity"),)

    topics: Mapped[list[Topic]] = relationship(back_populates="subject")
    papers: Mapped[list[Paper]] = relationship(back_populates="subject")


class Topic(Base):
    __tablename__ = "topics"

    id: Mapped[int] = mapped_column(primary_key=True)
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id"))
    name: Mapped[str] = mapped_column(String(100))
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("topics.id"))
    sort_order: Mapped[int] = mapped_column(default=0)

    __table_args__ = (UniqueConstraint("subject_id", "name", name="topic_name"),)

    subject: Mapped[Subject] = relationship(back_populates="topics")
    sub_parts: Mapped[list[SubPart]] = relationship(back_populates="topic")


class Paper(Base):
    __tablename__ = "papers"

    id: Mapped[int] = mapped_column(primary_key=True)
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id"))
    component: Mapped[int]
    variant: Mapped[int]
    session: Mapped[ExamSession] = mapped_column(Enum(ExamSession, name="exam_session"))
    year: Mapped[int]
    total_marks: Mapped[int]
    level: Mapped[str] = mapped_column(String(2))

    __table_args__ = (
        UniqueConstraint(
            "subject_id", "component", "variant", "session", "year", name="paper_identity"
        ),
        CheckConstraint("total_marks > 0", name="total_marks_positive"),
    )

    subject: Mapped[Subject] = relationship(back_populates="papers")
    questions: Mapped[list[Question]] = relationship(
        back_populates="paper", cascade="all, delete-orphan"
    )


class Question(Base):
    __tablename__ = "questions"

    id: Mapped[int] = mapped_column(primary_key=True)
    paper_id: Mapped[int] = mapped_column(ForeignKey("papers.id"))
    question_number: Mapped[int]

    __table_args__ = (UniqueConstraint("paper_id", "question_number", name="question_number"),)

    paper: Mapped[Paper] = relationship(back_populates="questions")
    sub_parts: Mapped[list[SubPart]] = relationship(
        back_populates="question", cascade="all, delete-orphan"
    )


class SubPart(Base):
    __tablename__ = "sub_parts"

    id: Mapped[int] = mapped_column(primary_key=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id"))
    label: Mapped[str] = mapped_column(String(10), default="")
    max_marks: Mapped[int]
    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id"))
    sort_order: Mapped[int] = mapped_column(default=0)

    __table_args__ = (
        UniqueConstraint("question_id", "label", name="sub_part_label"),
        CheckConstraint("max_marks > 0", name="max_marks_positive"),
    )

    question: Mapped[Question] = relationship(back_populates="sub_parts")
    topic: Mapped[Topic] = relationship(back_populates="sub_parts")
