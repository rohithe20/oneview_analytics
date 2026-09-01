from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.analytics import topic_performance
from app.services.insight import SubjectContext, select_insight
from app.services.prediction import AttemptPercentage, PredictionConfig, predict_performance
from app.services.priority import SubtopicStats, rank_priorities
from app.services.recommendation import select_recommendation
from app.services.trend import classify_trend

MIN_ATTEMPTS_FOR_SUFFICIENT_DATA = 5  # family-level gate, overview-assembly.md
RECENT_ERROR_WINDOW = 4  # priority-engine.md repeated-error footnote


@dataclass
class MetricSummary:
    average_percentage: float | None
    recent_percentage: float | None
    papers_completed: int
    target_value: int | None
    completion_percentage: float | None
    available_papers: int


@dataclass
class FamilyOverview:
    component_family: str
    exam_level: str

    predicted_percentage: float | None
    prediction_confidence: str

    metrics: MetricSummary

    trend_status: str
    trend_points: list[float]

    priorities: list  # list[PriorityArea]

    insight_text: str | None
    insight_rule_id: str

    recommendation_text: str | None
    recommendation_rule_id: str

    has_sufficient_data: bool
    attempts_count: int


def _fetch_attempts(db: Session, student_id: int, exam_level: str, component_family: str):
    """Scope-filtered completed attempts, oldest -> newest, from v_attempt_totals."""
    rows = db.execute(
        text("""
            SELECT percentage, completed_at
            FROM v_attempt_totals
            WHERE student_id = :student_id
              AND exam_level = :exam_level
              AND component_family = :component_family
              AND percentage IS NOT NULL
            ORDER BY completed_at ASC
        """),
        {
            "student_id": student_id,
            "exam_level": exam_level,
            "component_family": component_family,
        },
    ).all()
    return rows


def _fetch_topic_attempt_rows(db: Session, student_id: int, exam_level: str, component_family: str):
    """Per (topic, attempt) marks, oldest -> newest within each topic.

    v_topic_performance only gives topic-level totals; the priority engine
    also needs each topic's per-attempt history to derive the repeated-error
    signal and its own trend, so this queries the underlying tables directly
    with the same scope filter the views use.
    """
    rows = db.execute(
        text("""
            SELECT
                t.name AS topic_name,
                a.completed_at AS completed_at,
                SUM(r.marks_scored) AS marks_scored,
                SUM(sp.max_marks) AS marks_available
            FROM attempts a
            JOIN papers p           ON p.id = a.paper_id
            JOIN sub_part_results r ON r.attempt_id = a.id
            JOIN sub_parts sp       ON sp.id = r.sub_part_id
            JOIN topics t           ON t.id = sp.topic_id
            WHERE a.status = 'COMPLETED'
              AND a.student_id = :student_id
              AND p.level = :exam_level
              AND CASE
                    WHEN p.component IN (1, 3) THEN 'Pure'
                    WHEN p.component IN (5, 6) THEN 'Statistics'
                    ELSE 'Other'
                  END = :component_family
            GROUP BY t.name, a.id, a.completed_at
            ORDER BY t.name, a.completed_at ASC
        """),
        {
            "student_id": student_id,
            "exam_level": exam_level,
            "component_family": component_family,
        },
    ).mappings().all()
    return rows


def _fetch_target_value(
    db: Session, student_id: int, exam_level: str, component_family: str
) -> int | None:
    row = db.execute(
        text("""
            SELECT target_value FROM study_targets
            WHERE student_id = :student_id
              AND exam_level = :exam_level
              AND component_family = :component_family
        """),
        {
            "student_id": student_id,
            "exam_level": exam_level,
            "component_family": component_family,
        },
    ).first()
    return row[0] if row else None


def _fetch_available_papers(db: Session, exam_level: str, component_family: str) -> int:
    return db.execute(
        text("""
            SELECT COUNT(*)
            FROM papers p
            JOIN component_families cf ON cf.component = p.component
            WHERE p.level = :exam_level AND cf.family = :component_family
        """),
        {"exam_level": exam_level, "component_family": component_family},
    ).scalar_one()


def _build_subtopic_stats(
    topic_perf,
    topic_rows,
    family_avg: float | None,
) -> tuple[list[SubtopicStats], dict[str, tuple[str, int | None, int | None]]]:
    """Build SubtopicStats per topic plus the trend/error-count context the
    insight engine needs for whichever subtopic priority ranks first.

    `topic_perf` (from app.services.analytics.topic_performance, backed by
    v_topic_performance) supplies subtopic_avg/observation_count. `topic_rows`
    supplies the per-attempt history that view doesn't carry, needed for the
    repeated-error signal and this subtopic's own trend.

    topics.parent_id is dormant in V1 (no subtopic rows are seeded — see
    docs/data-model.md §3), so "subtopic" and "topic" are the same value
    here. Flagged per CLAUDE.md, not silently assumed.
    """
    by_topic: dict[str, list] = {}
    for row in topic_rows:
        by_topic.setdefault(row["topic_name"], []).append(row)

    stats: list[SubtopicStats] = []
    extra: dict[str, tuple[str, int | None, int | None]] = {}

    for tp in topic_perf:
        attempt_rows = by_topic.get(tp.topic_name, [])
        percentages = []
        has_error_flags = []
        for r in attempt_rows:
            available = r["marks_available"] or 0
            scored = r["marks_scored"] or 0
            if available <= 0:
                continue
            percentages.append(round(100.0 * scored / available, 2))
            has_error_flags.append(scored < available)

        trend_result = classify_trend(percentages)
        improving = trend_result.status == "Improving"

        window = has_error_flags[-RECENT_ERROR_WINDOW:]
        y = len(window)
        x = sum(1 for had_error in window if had_error)
        repeated_error_signal = y >= 3 and (x / y) >= 0.5
        recent_error_frequency = (x / y) if y else 0.0

        stats.append(
            SubtopicStats(
                topic=tp.topic_name,
                subtopic=tp.topic_name,
                subtopic_avg=float(tp.percentage) if tp.percentage is not None else 0.0,
                subject_avg=family_avg if family_avg is not None else 0.0,
                observation_count=tp.attempts_count,
                repeated_error_signal=repeated_error_signal,
                improving=improving,
                recent_error_frequency=recent_error_frequency,
            )
        )
        extra[tp.topic_name] = (trend_result.status, x if y else None, y if y else None)

    return stats, extra


def build_family_overview(
    db: Session,
    student_id: int,
    exam_level: str,
    component_family: str,
) -> FamilyOverview:
    attempt_rows = _fetch_attempts(db, student_id, exam_level, component_family)
    percentages = [float(r.percentage) for r in attempt_rows]
    saved_ats = [r.completed_at for r in attempt_rows]

    attempts_count = len(percentages)
    has_sufficient_data = attempts_count >= MIN_ATTEMPTS_FOR_SUFFICIENT_DATA

    average_percentage = round(sum(percentages) / attempts_count, 2) if attempts_count else None
    recent_percentage = percentages[-1] if percentages else None

    target_value = _fetch_target_value(db, student_id, exam_level, component_family)
    completion_percentage = (
        round(100.0 * attempts_count / target_value, 2) if target_value else None
    )
    available_papers = _fetch_available_papers(db, exam_level, component_family)

    metrics = MetricSummary(
        average_percentage=average_percentage,
        recent_percentage=recent_percentage,
        papers_completed=attempts_count,
        target_value=target_value,
        completion_percentage=completion_percentage,
        available_papers=available_papers,
    )

    attempt_percentages = [
        AttemptPercentage(percentage=p, saved_at=s)
        for p, s in zip(percentages, saved_ats, strict=True)
    ]
    # overview-assembly.md's FamilyOverview docstring lists prediction_confidence
    # as 'normal' | 'limited' | 'none', but prediction.py's PredictionResult
    # actually returns 'insufficient' for the no-prediction case. Passed
    # through as-is rather than remapped — this layer packs the engine's
    # output, it doesn't rename it. Flagged per CLAUDE.md, not guessed.
    prediction_result = predict_performance(
        attempt_percentages, PredictionConfig(allow_limited_data=True)
    )

    family_trend = classify_trend(percentages)

    topic_perf = topic_performance(db, student_id, exam_level, component_family)
    topic_rows = _fetch_topic_attempt_rows(db, student_id, exam_level, component_family)
    subtopic_stats, subtopic_extra = _build_subtopic_stats(
        topic_perf, topic_rows, average_percentage
    )

    priorities = rank_priorities(subtopic_stats)

    if priorities:
        top = priorities[0]
        trend_status, error_x, error_y = subtopic_extra.get(top.subtopic, (None, None, None))
        top_stat = next(
            (s for s in subtopic_stats if s.topic == top.topic and s.subtopic == top.subtopic),
            None,
        )
        subject_context = SubjectContext(
            sufficient_data=has_sufficient_data,
            subtopic=top.subtopic,
            topic=top.topic,
            subtopic_avg=top.percentage,
            subject_avg=average_percentage,
            trend_status=trend_status,
            repeated_error_signal=top_stat.repeated_error_signal if top_stat else False,
            repeated_error_x=error_x,
            repeated_error_y=error_y,
        )
    else:
        subject_context = SubjectContext(sufficient_data=has_sufficient_data)

    insight = select_insight(subject_context)
    recommendation = select_recommendation(insight, subject_context)

    return FamilyOverview(
        component_family=component_family,
        exam_level=exam_level,
        predicted_percentage=prediction_result.predicted_percentage,
        prediction_confidence=prediction_result.confidence,
        metrics=metrics,
        trend_status=family_trend.status,
        trend_points=percentages,
        priorities=priorities,
        insight_text=insight.text,
        insight_rule_id=insight.rule_id,
        recommendation_text=recommendation.text,
        recommendation_rule_id=recommendation.rule_id,
        has_sufficient_data=has_sufficient_data,
        attempts_count=attempts_count,
    )


__all__ = ["MetricSummary", "FamilyOverview", "build_family_overview"]
