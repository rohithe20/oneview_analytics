"""Topic Analysis — read-only diagnostic assembly (docs/specs/topic-analysis-service.md).

Assembles everything the Topic Analysis page shows for one scope
`(student_id, exam_level, component_family)`: five summary tiles, the eight
top-level topic rows, the subtopic rows for a selected topic, and the
question-level lost-mark records for a selected subtopic.

It introduces NO new formulas (BRD §1, §8, FSD §6):

- Average Performance, papers attempted/available, has_sufficient_data and the
  priority topic all come from `build_family_overview` — one source of truth,
  so this screen can never disagree with Overview.
- Status labels come from `priority.classify_status`, the shared threshold->label
  helper the priority engine's own classification feeds.
- The variant code comes from `paper_catalog.variant_display`.

The only genuinely new query is the question-level lost-mark list (§8).

Every read filters on (student_id, exam_level, component_family), reduced to the
most-recent completed attempt per distinct paper via v_latest_paper_attempts —
the same reduction Overview and the analytics views use.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.overview import RECENT_ERROR_WINDOW, build_family_overview
from app.services.paper_catalog import question_display_number, variant_display
from app.services.priority import (
    MIN_OBSERVATIONS,
    STATUS_INSUFFICIENT,
    SubtopicStats,
    classify_status,
)
from app.services.trend import classify_trend


@dataclass
class TopicRow:
    topic_id: int
    topic_name: str
    questions: int  # count of question outcomes for this topic
    average_score: float  # percentage
    marks_lost: int
    status: str  # Strong/Monitor/Needs Focus/High Priority/Insufficient data


@dataclass
class SubtopicRow:
    subtopic_id: int
    subtopic_name: str
    questions: int
    average_score: float
    marks_lost: int
    status: str


@dataclass
class LostMarkQuestion:
    year: int
    variant_display: str  # combined code e.g. "12"
    question: str  # e.g. "6(b)"
    your_score: int
    max_marks: int
    marks_lost: int


@dataclass
class TopicAnalysisSummary:
    papers_attempted: int  # "18 of 28 available" — attempted + available
    papers_available: int
    questions_analysed: int
    average_performance: float | None
    strongest_topic_name: str | None
    strongest_topic_pct: float | None
    priority_topic_name: str | None
    priority_topic_pct: float | None


@dataclass
class TopicAnalysisView:
    summary: TopicAnalysisSummary
    topics: list[TopicRow]  # all 8, sorted by syllabus order
    selected_topic_id: int | None  # default = priority topic
    subtopics: list[SubtopicRow]  # for selected topic
    selected_subtopic_id: int | None  # default = weakest eligible
    lost_mark_questions: list[LostMarkQuestion]  # for selected subtopic


# --- Data access -------------------------------------------------------------


def _fetch_leaf_attempt_rows(db: Session, student_id: int, exam_level: str, component_family: str):
    """Per (leaf topic, counted attempt) marks in scope, oldest -> newest.

    A sub_part points at the most specific topic level available — a subtopic
    where the seed maps one, else a top-level topic (docs/specs/subtopic-seed.md).
    Each row carries both that leaf and the top-level topic it rolls up to
    (its parent, or itself when it has no parent), so the caller can aggregate to
    either granularity from one query. Reduced to the most-recent attempt per
    distinct paper via v_latest_paper_attempts, and scope-filtered through the
    component_families reference table (never a hard-coded component list).
    """
    return (
        db.execute(
            text("""
            SELECT
                leaf.id                              AS leaf_id,
                leaf.name                            AS leaf_name,
                leaf.sort_order                      AS leaf_sort,
                COALESCE(parent.id, leaf.id)         AS top_id,
                COALESCE(parent.name, leaf.name)     AS top_name,
                COALESCE(parent.sort_order, leaf.sort_order) AS top_sort,
                a.id                                 AS attempt_id,
                a.completed_at                       AS completed_at,
                SUM(r.marks_scored)                  AS marks_scored,
                SUM(sp.max_marks)                    AS marks_available,
                COUNT(*)                             AS outcomes
            FROM attempts a
            JOIN v_latest_paper_attempts la ON la.attempt_id = a.id
            JOIN papers p             ON p.id = a.paper_id
            JOIN component_families cf ON cf.component = p.component
            JOIN sub_part_results r   ON r.attempt_id = a.id
            JOIN sub_parts sp         ON sp.id = r.sub_part_id
            JOIN topics leaf          ON leaf.id = sp.topic_id
            LEFT JOIN topics parent   ON parent.id = leaf.parent_id
            WHERE a.status = 'COMPLETED'
              AND a.student_id = :student_id
              AND p.level = :exam_level
              AND cf.family = :component_family
            GROUP BY leaf.id, leaf.name, leaf.sort_order,
                     parent.id, parent.name, parent.sort_order,
                     a.id, a.completed_at
            ORDER BY completed_at ASC
        """),
            {
                "student_id": student_id,
                "exam_level": exam_level,
                "component_family": component_family,
            },
        )
        .mappings()
        .all()
    )


def _fetch_topics_in_scope(db: Session, exam_level: str, component_family: str):
    """The top-level topics that belong to this (level, family), syllabus order.

    Topics carry no family column — a topic is "in scope" when one of its
    sub_parts appears in a paper of this level and family (derived from the
    seeded question structure, not from student attempts, so all eight show even
    before anything is recorded). This keeps Statistics topics out of a Pure
    view and vice versa without a topics->family link the schema does not have.
    """
    return (
        db.execute(
            text("""
            SELECT top.id AS topic_id, top.name AS topic_name
            FROM topics top
            WHERE top.parent_id IS NULL
              AND EXISTS (
                  SELECT 1
                  FROM sub_parts sp
                  JOIN topics leaf     ON leaf.id = sp.topic_id
                  JOIN questions q     ON q.id = sp.question_id
                  JOIN papers p        ON p.id = q.paper_id
                  JOIN component_families cf ON cf.component = p.component
                  WHERE COALESCE(leaf.parent_id, leaf.id) = top.id
                    AND p.level = :exam_level
                    AND cf.family = :component_family
              )
            ORDER BY top.sort_order
        """),
            {"exam_level": exam_level, "component_family": component_family},
        )
        .mappings()
        .all()
    )


def _fetch_subtopics(db: Session, topic_id: int):
    """All taxonomy children of `topic_id`, syllabus order (§7 step 2).

    The full seeded list, so a subtopic with no in-scope observations still
    appears (as "Insufficient data") rather than vanishing.
    """
    return (
        db.execute(
            text("""
            SELECT id AS subtopic_id, name AS subtopic_name
            FROM topics
            WHERE parent_id = :topic_id
            ORDER BY sort_order
        """),
            {"topic_id": topic_id},
        )
        .mappings()
        .all()
    )


def _fetch_lost_mark_questions(
    db: Session, student_id: int, exam_level: str, component_family: str, subtopic_id: int
):
    """Question-level lost-mark records for one subtopic in scope (§8, FSD §9).

    The one new query: only the most-recent attempt per paper, only rows that
    lost marks (max_marks - marks_scored > 0), sorted by marks lost descending.
    No question text and no paper-opening identity beyond year/variant (§12).
    """
    return (
        db.execute(
            text("""
            SELECT
                p.year                        AS year,
                p.component                   AS component,
                p.variant                     AS variant,
                q.question_number             AS question_number,
                sp.label                      AS label,
                r.marks_scored                AS your_score,
                sp.max_marks                  AS max_marks,
                (sp.max_marks - r.marks_scored) AS marks_lost
            FROM sub_part_results r
            JOIN attempts a           ON a.id = r.attempt_id
            JOIN v_latest_paper_attempts la ON la.attempt_id = a.id
            JOIN papers p             ON p.id = a.paper_id
            JOIN component_families cf ON cf.component = p.component
            JOIN sub_parts sp         ON sp.id = r.sub_part_id
            JOIN questions q          ON q.id = sp.question_id
            WHERE a.status = 'COMPLETED'
              AND a.student_id = :student_id
              AND p.level = :exam_level
              AND cf.family = :component_family
              AND sp.topic_id = :subtopic_id
              AND (sp.max_marks - r.marks_scored) > 0
            ORDER BY marks_lost DESC, p.year DESC, q.question_number, sp.label
        """),
            {
                "student_id": student_id,
                "exam_level": exam_level,
                "component_family": component_family,
                "subtopic_id": subtopic_id,
            },
        )
        .mappings()
        .all()
    )


# --- Aggregation -------------------------------------------------------------


@dataclass
class _GroupAgg:
    """One topic's or subtopic's rolled-up numbers plus the engine inputs."""

    questions: int
    marks_lost: int
    average_score: float
    stat: SubtopicStats


def _aggregate_group(per_attempt: list[dict], subject_avg: float) -> _GroupAgg:
    """Roll one group's per-attempt records up into a row + a SubtopicStats.

    `per_attempt` is one record per counted attempt (already summed across the
    group's leaves), oldest -> newest. The status inputs (trend/improving and
    the repeated-error signal) are derived exactly as Overview derives them so
    classify_status sees the same rule the priority engine does.
    """
    total_scored = sum(r["marks_scored"] for r in per_attempt)
    total_available = sum(r["marks_available"] for r in per_attempt)
    outcomes = sum(r["outcomes"] for r in per_attempt)
    marks_lost = total_available - total_scored
    observation_count = len(per_attempt)
    average = round(100.0 * total_scored / total_available, 2) if total_available else 0.0

    percentages: list[float] = []
    error_flags: list[bool] = []
    for r in per_attempt:
        available = r["marks_available"] or 0
        if available <= 0:
            continue
        percentages.append(round(100.0 * r["marks_scored"] / available, 2))
        error_flags.append(r["marks_scored"] < available)

    improving = classify_trend(percentages).status == "Improving"
    window = error_flags[-RECENT_ERROR_WINDOW:]
    y = len(window)
    x = sum(1 for had_error in window if had_error)
    repeated_error_signal = y >= 3 and (x / y) >= 0.5
    recent_error_frequency = (x / y) if y else 0.0

    stat = SubtopicStats(
        topic="",
        subtopic="",
        subtopic_avg=average,
        subject_avg=subject_avg,
        observation_count=observation_count,
        repeated_error_signal=repeated_error_signal,
        improving=improving,
        recent_error_frequency=recent_error_frequency,
    )
    return _GroupAgg(questions=outcomes, marks_lost=marks_lost, average_score=average, stat=stat)


def _combine_leaves_by_attempt(rows: list[dict]) -> dict[int, dict]:
    """Sum leaf rows sharing an attempt into one per-attempt record for a topic.

    A top-level topic spans several leaves; within one attempt its marks are the
    sum over those leaves. Keyed by attempt_id, keeping the attempt's
    completed_at for ordering.
    """
    by_attempt: dict[int, dict] = {}
    for r in rows:
        rec = by_attempt.get(r["attempt_id"])
        if rec is None:
            by_attempt[r["attempt_id"]] = {
                "attempt_id": r["attempt_id"],
                "completed_at": r["completed_at"],
                "marks_scored": r["marks_scored"] or 0,
                "marks_available": r["marks_available"] or 0,
                "outcomes": r["outcomes"] or 0,
            }
        else:
            rec["marks_scored"] += r["marks_scored"] or 0
            rec["marks_available"] += r["marks_available"] or 0
            rec["outcomes"] += r["outcomes"] or 0
    return by_attempt


def _ordered(records: dict[int, dict]) -> list[dict]:
    return sorted(records.values(), key=lambda r: (r["completed_at"], r["attempt_id"]))


def _status(agg: _GroupAgg | None, has_sufficient_data: bool) -> str:
    """The status for one row.

    Below the overall reliability gate (<5 papers), reliability-dependent
    statuses collapse to "Insufficient data" (§10, FSD §10). With no
    observations at all, likewise. Otherwise the shared classifier decides.
    """
    if agg is None or not has_sufficient_data:
        return STATUS_INSUFFICIENT
    return classify_status(agg.stat)


# --- Assembly ----------------------------------------------------------------


def build_topic_analysis(
    db: Session,
    student_id: int,
    exam_level: str,
    component_family: str,
    selected_topic_id: int | None = None,
    selected_subtopic_id: int | None = None,
) -> TopicAnalysisView:
    # One source of truth for the shared numbers: Average Performance, papers
    # attempted/available, the reliability gate and the priority topic all come
    # from Overview, so the two screens can never disagree (BRD §8).
    overview = build_family_overview(db, student_id, exam_level, component_family)
    subject_avg = overview.metrics.average_percentage or 0.0
    has_sufficient_data = overview.has_sufficient_data

    leaf_rows = _fetch_leaf_attempt_rows(db, student_id, exam_level, component_family)

    # Roll leaf rows up to their top-level topic, then aggregate each topic.
    leaves_by_top: dict[int, list[dict]] = {}
    for r in leaf_rows:
        leaves_by_top.setdefault(r["top_id"], []).append(r)
    topic_aggs: dict[int, _GroupAgg] = {
        top_id: _aggregate_group(_ordered(_combine_leaves_by_attempt(rows)), subject_avg)
        for top_id, rows in leaves_by_top.items()
    }

    topics_in_scope = _fetch_topics_in_scope(db, exam_level, component_family)
    topics: list[TopicRow] = []
    for t in topics_in_scope:
        agg = topic_aggs.get(t["topic_id"])
        topics.append(
            TopicRow(
                topic_id=t["topic_id"],
                topic_name=t["topic_name"],
                questions=agg.questions if agg else 0,
                average_score=agg.average_score if agg else 0.0,
                marks_lost=agg.marks_lost if agg else 0,
                status=_status(agg, has_sufficient_data),
            )
        )

    questions_analysed = sum(t.questions for t in topics)

    # Strongest and priority topics (summary tiles). Strongest = highest average
    # among topics with observations. Priority topic = the topic the priority
    # engine ranks first (via Overview), NOT simply highest marks lost (§6, §32).
    topics_with_data = [t for t in topics if topic_aggs.get(t.topic_id) is not None]
    strongest = max(topics_with_data, key=lambda t: t.average_score, default=None)

    name_to_topic = {t.topic_name: t for t in topics}
    priority_topic: TopicRow | None = None
    if overview.priorities:
        priority_topic = name_to_topic.get(overview.priorities[0].topic)
    if priority_topic is None:
        # No ranked priority (e.g. insufficient data): fall back to the weakest
        # topic that has data, else the first topic, so a default still exists.
        priority_topic = min(
            topics_with_data, key=lambda t: t.average_score, default=None
        ) or (topics[0] if topics else None)

    # Selected topic: caller's choice, else the priority topic (§7 default).
    if selected_topic_id is not None:
        selected_topic = name_to_topic_by_id(topics, selected_topic_id)
    else:
        selected_topic = priority_topic
    resolved_topic_id = selected_topic.topic_id if selected_topic else None

    # Subtopic rows for the selected topic.
    subtopics: list[SubtopicRow] = []
    subtopic_aggs: dict[int, _GroupAgg] = {}
    if resolved_topic_id is not None:
        leaves_of_selected = [r for r in leaf_rows if r["top_id"] == resolved_topic_id]
        by_leaf: dict[int, list[dict]] = {}
        for r in leaves_of_selected:
            by_leaf.setdefault(r["leaf_id"], []).append(r)
        subtopic_aggs = {
            leaf_id: _aggregate_group(_ordered(_combine_leaves_by_attempt(rows)), subject_avg)
            for leaf_id, rows in by_leaf.items()
        }
        for s in _fetch_subtopics(db, resolved_topic_id):
            agg = subtopic_aggs.get(s["subtopic_id"])
            subtopics.append(
                SubtopicRow(
                    subtopic_id=s["subtopic_id"],
                    subtopic_name=s["subtopic_name"],
                    questions=agg.questions if agg else 0,
                    average_score=agg.average_score if agg else 0.0,
                    marks_lost=agg.marks_lost if agg else 0,
                    status=_status(agg, has_sufficient_data),
                )
            )

    # Selected subtopic: caller's choice, else the weakest eligible subtopic
    # (lowest average among those with >= 3 observations) (§7 step 3).
    if selected_subtopic_id is not None:
        resolved_subtopic_id = selected_subtopic_id
    else:
        eligible = [
            s
            for s in subtopics
            if (agg := subtopic_aggs.get(s.subtopic_id)) is not None
            and agg.stat.observation_count >= MIN_OBSERVATIONS
        ]
        weakest = min(eligible, key=lambda s: s.average_score, default=None)
        resolved_subtopic_id = weakest.subtopic_id if weakest else None

    lost_mark_questions: list[LostMarkQuestion] = []
    if resolved_subtopic_id is not None:
        for row in _fetch_lost_mark_questions(
            db, student_id, exam_level, component_family, resolved_subtopic_id
        ):
            lost_mark_questions.append(
                LostMarkQuestion(
                    year=row["year"],
                    variant_display=variant_display(row["component"], row["variant"]),
                    question=question_display_number(row["question_number"], row["label"]),
                    your_score=row["your_score"],
                    max_marks=row["max_marks"],
                    marks_lost=row["marks_lost"],
                )
            )

    summary = TopicAnalysisSummary(
        papers_attempted=overview.metrics.papers_completed,
        papers_available=overview.metrics.available_papers,
        questions_analysed=questions_analysed,
        average_performance=overview.metrics.average_percentage,
        strongest_topic_name=strongest.topic_name if strongest else None,
        strongest_topic_pct=strongest.average_score if strongest else None,
        priority_topic_name=priority_topic.topic_name if priority_topic else None,
        priority_topic_pct=priority_topic.average_score if priority_topic else None,
    )

    return TopicAnalysisView(
        summary=summary,
        topics=topics,
        selected_topic_id=resolved_topic_id,
        subtopics=subtopics,
        selected_subtopic_id=resolved_subtopic_id,
        lost_mark_questions=lost_mark_questions,
    )


def name_to_topic_by_id(topics: list[TopicRow], topic_id: int) -> TopicRow | None:
    return next((t for t in topics if t.topic_id == topic_id), None)


__all__ = [
    "TopicRow",
    "SubtopicRow",
    "LostMarkQuestion",
    "TopicAnalysisSummary",
    "TopicAnalysisView",
    "build_topic_analysis",
]
