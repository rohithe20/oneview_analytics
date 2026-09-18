"""Practice-target reads and writes (docs/specs/planning-performance.md).

Everything here is scoped to (student_id, exam_level, component_family) —
the BRD §32 invariant. Available Papers is counted through the
component_families lookup table, never a hard-coded component list.
"""

from __future__ import annotations

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models import StudyTarget


class TargetValidationError(ValueError):
    """A practice target outside 0 <= value <= available_papers (OV-PL-003)."""


def get_available_papers(db: Session, exam_level: str, component_family: str) -> int:
    """Eligible papers in the paper DB for this scope. System-controlled (§17).

    component_families is reference data created and seeded by migration
    15047ca50390, not an ORM model, so this reads it as SQL — the same way
    the analytics views do.
    """
    return db.execute(
        text("""
            SELECT COUNT(*)
            FROM papers p
            JOIN component_families cf ON cf.component = p.component
            WHERE p.level = :exam_level AND cf.family = :component_family
        """),
        {"exam_level": exam_level, "component_family": component_family},
    ).scalar_one()


def get_target(
    db: Session, student_id: int, exam_level: str, component_family: str
) -> StudyTarget | None:
    """The stored StudyTarget for this scope, or None when never set."""
    return db.scalar(
        select(StudyTarget).where(
            StudyTarget.student_id == student_id,
            StudyTarget.exam_level == exam_level,
            StudyTarget.component_family == component_family,
        )
    )


def set_target(
    db: Session,
    student_id: int,
    exam_level: str,
    component_family: str,
    value: int,
) -> StudyTarget:
    """Upsert the practice target for one scope.

    Validates 0 <= value <= available_papers (OV-PL-003), raising
    TargetValidationError on violation. Writing a target only touches
    study_targets — historical attempts and analytics are never altered
    (OV-PL-007, §28).
    """
    available_papers = get_available_papers(db, exam_level, component_family)
    if value < 0 or value > available_papers:
        raise TargetValidationError(
            f"Target must be between 0 and {available_papers} "
            f"— the papers available for {exam_level} {component_family}."
        )

    target = get_target(db, student_id, exam_level, component_family)
    if target is None:
        target = StudyTarget(
            student_id=student_id,
            exam_level=exam_level,
            component_family=component_family,
            target_value=value,
        )
        db.add(target)
    else:
        target.target_value = value

    db.commit()
    return target


__all__ = [
    "TargetValidationError",
    "get_available_papers",
    "get_target",
    "set_target",
]
