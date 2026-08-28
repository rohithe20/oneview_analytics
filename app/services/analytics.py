from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session

MIN_ATTEMPTS_FOR_JUDGEMENT = 3  # BR-05


@dataclass
class TopicPerformance:
    topic_id: int
    topic_name: str
    marks_scored: int
    marks_available: int
    marks_lost: int
    percentage: float
    attempts_count: int
    sufficient_data: bool


def topic_performance(
    db: Session,
    student_id: int,
    exam_level: str,
    component_family: str,
) -> list[TopicPerformance]:
    rows = db.execute(
        text("""
            SELECT topic_id, topic_name, marks_scored, marks_available,
                   marks_lost, percentage, attempts_count
            FROM v_topic_performance
            WHERE student_id = :student_id
              AND exam_level = :exam_level
              AND component_family = :component_family
            ORDER BY sort_order
        """),
        {
            "student_id": student_id,
            "exam_level": exam_level,
            "component_family": component_family,
        },
    ).mappings()

    return [
        TopicPerformance(
            **row,
            sufficient_data=row["attempts_count"] >= MIN_ATTEMPTS_FOR_JUDGEMENT,
        )
        for row in rows
    ]
