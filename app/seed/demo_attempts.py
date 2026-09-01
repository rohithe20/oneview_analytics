from __future__ import annotations

import random
import sys
from datetime import datetime, timedelta

from sqlalchemy import select

from app.core.db import SessionLocal
from app.models import Attempt, Paper, Student, SubPart, SubPartResult
from app.models.enums import AttemptStatus

DEMO_STUDENT_USERNAME = "demo_student"
DEMO_MARKER_PREFIX = "[DEMO]"  # stored in attempt notes for identification

# A subtopic name the demo student is deliberately weak at, so priority
# and insight have a clear story. Use a real topic name from your seed.
WEAK_TOPIC_NAME = "Integration"

random.seed(42)  # reproducible demo data


def get_or_create_demo_student(db) -> Student:
    student = db.scalar(
        select(Student).where(Student.username == DEMO_STUDENT_USERNAME)
    )
    if student is None:
        student = Student(
            username=DEMO_STUDENT_USERNAME,
            display_name="Laya Eshwarwak",
            level="AS",
            password_hash="not-a-real-hash",
        )
        db.add(student)
        db.flush()
    return student


def wipe_demo_attempts(db, student: Student) -> int:
    attempts = db.scalars(
        select(Attempt).where(Attempt.student_id == student.id)
    ).all()
    n = 0
    for a in attempts:
        if (a.notes or "").startswith(DEMO_MARKER_PREFIX):
            db.delete(a)  # cascade removes sub_part_results
            n += 1
    return n


def score_for_subpart(sub_part: SubPart, topic_name: str, base_ability: float) -> int:
    """Return marks_scored for one sub-part.

    base_ability is the student's rough proficiency (0-1). The weak topic
    is scored markedly lower so it surfaces as a priority.
    """
    ability = base_ability
    if topic_name == WEAK_TOPIC_NAME:
        ability = max(0.15, base_ability - 0.4)  # deliberate weakness
    # add a little noise, clamp to [0, max_marks]
    frac = min(1.0, max(0.0, random.gauss(ability, 0.12)))
    return round(frac * sub_part.max_marks)


def seed_demo_attempts(db, student: Student, num_attempts: int = 6) -> int:
    # Pick papers to attempt — take the seeded papers in scope.
    papers = db.scalars(select(Paper).order_by(Paper.year, Paper.component)).all()
    if not papers:
        raise SystemExit(
            "No papers seeded. Run `python -m app.seed` first."
        )

    # Simulate improvement over time: base ability rises across attempts,
    # so the trend reads as Improving and the prediction is meaningful.
    created = 0
    start = datetime(2026, 2, 1)
    for i in range(num_attempts):
        paper = papers[i % len(papers)]
        base_ability = 0.55 + 0.03 * i  # gently improving

        attempt = Attempt(
            student_id=student.id,
            paper_id=paper.id,
            status=AttemptStatus.COMPLETED,
            notes=f"{DEMO_MARKER_PREFIX} synthetic attempt {i + 1}",
            completed_at=start + timedelta(days=7 * i),
        )
        db.add(attempt)
        db.flush()

        # Load every sub-part of the paper and score it.
        sub_parts = db.scalars(
            select(SubPart)
            .join(SubPart.question)
            .where(SubPart.question.has(paper_id=paper.id))
        ).all()

        for sp in sub_parts:
            topic_name = sp.topic.name if sp.topic else ""
            marks = score_for_subpart(sp, topic_name, base_ability)
            db.add(
                SubPartResult(
                    attempt_id=attempt.id,
                    sub_part_id=sp.id,
                    marks_scored=marks,
                )
            )
        created += 1

    return created


def main() -> int:
    wipe_only = "--wipe" in sys.argv
    with SessionLocal() as db:
        student = get_or_create_demo_student(db)
        removed = wipe_demo_attempts(db, student)
        if wipe_only:
            db.commit()
            print(f"Removed {removed} demo attempt(s).")
            return 0

        created = seed_demo_attempts(db, student)
        db.commit()
        print(
            f"Removed {removed} old demo attempt(s), created {created} new one(s) "
            f"for student '{student.username}' (id={student.id})."
        )
        print(f"Deliberate weak topic: {WEAK_TOPIC_NAME}")
        return 0


if __name__ == "__main__":
    sys.exit(main())


