from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Paper, Question, Subject, SubPart, Topic
from app.models.enums import ExamSession

DATA_DIR = Path(__file__).parent / "data"


class SeedError(Exception):
    """Raised when seed data is invalid. Aborts the whole load"""

    pass


def read_csv(filename: str) -> list[dict[str, str]]:
    path = DATA_DIR / filename
    if not path.exists():
        raise SeedError(f"Missing seed file: {path}")

    with path.open(newline="", encoding="utf-8-sig") as f:
        return [{k: (v or "").strip() for k, v in row.items()} for row in csv.DictReader(f)]


def load_subjects(db: Session) -> dict[str, Subject]:
    for row in read_csv("subjects.csv"):
        existing = db.scalar(
            select(Subject).where(Subject.board == row["board"], Subject.code == row["code"])
        )
        if existing is None:
            db.add(Subject(board=row["board"], code=row["code"], name=row["name"]))

    db.flush()
    return {s.code: s for s in db.scalars(select(Subject)).all()}


def load_topics(db: Session, subjects: dict[str, Subject]) -> dict[tuple[str, str], Topic]:
    errors: list[str] = []
    rows = list(enumerate(read_csv("topics.csv"), start=2))

    # Pass 1: top-level topics (blank parent_topic). Subtopics resolve
    # against these, so they must exist first.
    top_rows = [(i, row) for i, row in rows if not row["parent_topic"]]
    sub_rows = [(i, row) for i, row in rows if row["parent_topic"]]

    for i, row in top_rows:
        subject = subjects.get(row["subject_code"])
        if subject is None:
            errors.append(f"topics.csv line {i}: unknown subject_code {row['subject_code']!r}")
            continue

        existing = db.scalar(
            select(Topic).where(Topic.subject_id == subject.id, Topic.name == row["name"])
        )
        if existing is None:
            db.add(
                Topic(
                    subject_id=subject.id,
                    name=row["name"],
                    parent_id=None,
                    sort_order=int(row["sort_order"] or 0),
                )
            )

    if errors:
        raise SeedError("\n".join(errors))

    db.flush()

    # Names of rows in this file that are themselves subtopics — used to
    # give a precise error when a subtopic tries to parent another one.
    subtopic_names_in_file = {row["name"] for _, row in sub_rows}

    top_level_by_name: dict[tuple[str, str], Topic] = {
        (t.subject.code, t.name): t
        for t in db.scalars(select(Topic).where(Topic.parent_id.is_(None))).all()
    }

    # Pass 2: subtopics, one level of nesting only.
    for i, row in sub_rows:
        subject = subjects.get(row["subject_code"])
        if subject is None:
            errors.append(f"topics.csv line {i}: unknown subject_code {row['subject_code']!r}")
            continue

        parent_name = row["parent_topic"]

        if parent_name in subtopic_names_in_file:
            errors.append(
                f"topics.csv line {i}: parent_topic {parent_name!r} for subtopic "
                f"{row['name']!r} is itself a subtopic — only one level of nesting is allowed"
            )
            continue

        parent = top_level_by_name.get((subject.code, parent_name))
        if parent is None:
            errors.append(
                f"topics.csv line {i}: unknown parent_topic {parent_name!r} "
                f"for subtopic {row['name']!r}"
            )
            continue

        existing = db.scalar(
            select(Topic).where(Topic.subject_id == subject.id, Topic.name == row["name"])
        )
        if existing is None:
            db.add(
                Topic(
                    subject_id=subject.id,
                    name=row["name"],
                    parent_id=parent.id,
                    sort_order=int(row["sort_order"] or 0),
                )
            )

    if errors:
        raise SeedError("\n".join(errors))

    db.flush()
    return {(t.subject.code, t.name): t for t in db.scalars(select(Topic)).all()}


def load_papers(db: Session, subjects: dict[str, Subject]) -> dict[str, Paper]:
    errors: list[str] = []
    by_ref: dict[str, Paper] = {}

    for i, row in enumerate(read_csv("papers.csv"), start=2):
        subject = subjects.get(row["subject_code"])
        if subject is None:
            errors.append(f"papers.csv line {i}: unknown subject_code {row['subject_code']!r}")
            continue

        try:
            session_enum = ExamSession[row["session"]]
        except KeyError:
            valid = ", ".join(s.name for s in ExamSession)
            errors.append(f"papers.csv line {i}: session must be one of {valid}")
            continue

        component, variant = int(row["component"]), int(row["variant"])
        year = int(row["year"])

        paper = db.scalar(
            select(Paper).where(
                Paper.subject_id == subject.id,
                Paper.component == component,
                Paper.variant == variant,
                Paper.session == session_enum,
                Paper.year == year,
            )
        )
        if paper is None:
            paper = Paper(
                subject_id=subject.id,
                component=component,
                variant=variant,
                session=session_enum,
                year=year,
                total_marks=int(row["total_marks"]),
                level=row["level"],
            )
            db.add(paper)

        by_ref[row["paper_ref"]] = paper

    if errors:
        raise SeedError("\n".join(errors))

    db.flush()
    return by_ref


def load_questions(
    db: Session,
    papers: dict[str, Paper],
    topics: dict[tuple[str, str], Topic],
) -> None:
    rows = read_csv("questions.csv")
    errors: list[str] = []

    # Group rows by (paper_ref, question_number), preserving file order.
    grouped: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[(row["paper_ref"], row["question_number"])].append(row)

    seen_labels: dict[tuple[str, str], set[str]] = defaultdict(set)
    totals: dict[str, int] = defaultdict(int)

    for (paper_ref, q_number), q_rows in grouped.items():
        paper = papers.get(paper_ref)
        if paper is None:
            errors.append(f"questions.csv: unknown paper_ref {paper_ref!r}")
            continue

        question = db.scalar(
            select(Question).where(
                Question.paper_id == paper.id,
                Question.question_number == int(q_number),
            )
        )
        if question is None:
            question = Question(paper_id=paper.id, question_number=int(q_number))
            db.add(question)
            db.flush()

        for order, row in enumerate(q_rows, start=1):
            label = row["sub_part_label"]

            if label in seen_labels[(paper_ref, q_number)]:
                errors.append(
                    f"questions.csv: duplicate part {label or '(none)'} "
                    f"on Q{q_number} of {paper_ref}"
                )
                continue
            seen_labels[(paper_ref, q_number)].add(label)

            topic = topics.get((paper.subject.code, row["topic_name"]))
            if topic is None:
                errors.append(
                    f"questions.csv: unknown topic {row['topic_name']!r} "
                    f"on Q{q_number}{label} of {paper_ref}"
                )
                continue

            marks = int(row["max_marks"])
            if marks <= 0:
                errors.append(
                    f"questions.csv: max_marks must be positive on Q{q_number} of {paper_ref}"
                )
                continue

            totals[paper_ref] += marks

            existing = db.scalar(
                select(SubPart).where(SubPart.question_id == question.id, SubPart.label == label)
            )
            if existing is None:
                db.add(
                    SubPart(
                        question_id=question.id,
                        label=label,
                        max_marks=marks,
                        topic_id=topic.id,
                        sort_order=order,
                    )
                )

    # The checksum: transcribed total must match the sum of the parts.
    for paper_ref, total in totals.items():
        paper = papers.get(paper_ref)
        if paper and total != paper.total_marks:
            errors.append(
                f"{paper_ref}: parts sum to {total} but paper total_marks is "
                f"{paper.total_marks} — check for a missing or mistyped row"
            )

    if errors:
        raise SeedError("\n".join(errors))
