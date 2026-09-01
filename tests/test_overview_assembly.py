"""Tests for the overview assembly layer — the seam between the engines
and the Overview page.

Agent: implement app/services/overview.py per
docs/specs/overview-assembly.md to make these pass.

Per the spec's test contract, these tests cover:
  1. A populated FamilyOverview for a student with >=5 Pure AS attempts,
     including a non-empty priorities list when a weak subtopic exists.
  2. has_sufficient_data is False with <5 attempts, with no fabricated
     weakness/numbers.
  3. Scope isolation: an attempt in another scope never leaks in.
  4. The assembly layer calls the trend engine rather than reimplementing
     it (trend_status must match classify_trend on the same percentages).

topics.parent_id is dormant in V1 (docs/data-model.md §3 — no subtopic
rows are seeded), so every seeded topic acts as its own subtopic here;
"Integration" is used as the deliberately weak one, scored at 0 marks
every attempt against full marks everywhere else.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select, text

from app.models import Attempt, Paper, Question, Student, SubPart, SubPartResult
from app.models.enums import AttemptStatus, ExamSession
from app.seed.loader import load_papers, load_questions, load_subjects, load_topics
from app.services.overview import build_family_overview
from app.services.trend import classify_trend

WEAK_TOPIC = "Integration"
PAPER_REF = "9709_11_MJ_2025"


def _seed_reference_data(db):
    subjects = load_subjects(db)
    topics = load_topics(db, subjects)
    papers = load_papers(db, subjects)
    load_questions(db, papers, topics)
    db.commit()
    return subjects, topics, papers


def _make_student(db) -> Student:
    student = Student(
        username="overview_test_student",
        display_name="Test Student",
        level="AS",
        password_hash="not-a-real-hash",
    )
    db.add(student)
    db.flush()
    return student


def _score_sub_part(sub_part: SubPart) -> int:
    """Full marks everywhere except the deliberately weak topic."""
    if sub_part.topic.name == WEAK_TOPIC:
        return 0
    return sub_part.max_marks


def _record_attempt(db, student: Student, paper: Paper, completed_at: datetime) -> Attempt:
    attempt = Attempt(
        student_id=student.id,
        paper_id=paper.id,
        status=AttemptStatus.COMPLETED,
        completed_at=completed_at,
    )
    db.add(attempt)
    db.flush()

    sub_parts = db.scalars(
        select(SubPart).join(SubPart.question).where(SubPart.question.has(paper_id=paper.id))
    ).all()
    for sp in sub_parts:
        db.add(
            SubPartResult(
                attempt_id=attempt.id, sub_part_id=sp.id, marks_scored=_score_sub_part(sp)
            )
        )
    db.commit()
    return attempt


# --- Populated panel with a weak subtopic ---


def test_populated_overview_with_sufficient_data(db_session):
    subjects, topics, papers = _seed_reference_data(db_session)
    student = _make_student(db_session)
    paper = papers[PAPER_REF]

    start = datetime(2026, 1, 1)
    for i in range(5):
        _record_attempt(db_session, student, paper, start + timedelta(days=7 * i))

    overview = build_family_overview(db_session, student.id, "AS", "Pure")

    assert overview.component_family == "Pure"
    assert overview.exam_level == "AS"
    assert overview.attempts_count == 5
    assert overview.has_sufficient_data is True

    assert overview.predicted_percentage is not None
    assert overview.prediction_confidence == "normal"

    assert overview.metrics.papers_completed == 5
    assert overview.metrics.average_percentage == 88.0
    assert overview.metrics.recent_percentage == 88.0

    # Integration is scored 0 every time against full marks elsewhere, so
    # it's the only subtopic with a qualifying gap.
    assert len(overview.priorities) == 1
    assert overview.priorities[0].subtopic == WEAK_TOPIC
    assert overview.priorities[0].priority == "High"

    assert overview.insight_rule_id == "INS-02"
    assert overview.insight_text == (
        "You have made errors in Integration in 4 of your last 4 relevant attempts."
    )
    assert overview.recommendation_rule_id == "REC-02"


# --- Insufficient data: no fabricated weakness or numbers ---


def test_insufficient_data_below_five_attempts(db_session):
    subjects, topics, papers = _seed_reference_data(db_session)
    student = _make_student(db_session)
    paper = papers[PAPER_REF]

    start = datetime(2026, 1, 1)
    for i in range(2):
        _record_attempt(db_session, student, paper, start + timedelta(days=7 * i))

    overview = build_family_overview(db_session, student.id, "AS", "Pure")

    assert overview.attempts_count == 2
    assert overview.has_sufficient_data is False
    assert overview.trend_status == "More data needed"

    # Only 2 observations per subtopic — below the priority engine's
    # minimum of 3, so nothing may be classified as weak.
    assert overview.priorities == []

    assert overview.insight_rule_id == "INS-05"
    assert overview.insight_text == (
        "More practice data is needed before OneView can reliably assess this area."
    )
    assert overview.recommendation_rule_id == "REC-06"


def test_empty_scope_has_no_fabricated_values(db_session):
    subjects, topics, papers = _seed_reference_data(db_session)
    student = _make_student(db_session)

    overview = build_family_overview(db_session, student.id, "AS", "Pure")

    assert overview.attempts_count == 0
    assert overview.has_sufficient_data is False
    assert overview.predicted_percentage is None
    assert overview.metrics.average_percentage is None
    assert overview.metrics.recent_percentage is None
    assert overview.priorities == []
    assert overview.insight_rule_id == "INS-05"


# --- Scope isolation ---


def test_scope_isolation_ignores_other_family_and_level(db_session):
    subjects, topics, papers = _seed_reference_data(db_session)
    student = _make_student(db_session)
    pure_paper = papers[PAPER_REF]

    start = datetime(2026, 1, 1)
    for i in range(5):
        _record_attempt(db_session, student, pure_paper, start + timedelta(days=7 * i))

    baseline = build_family_overview(db_session, student.id, "AS", "Pure")

    # A completed attempt in a different scope: same subject, Statistics
    # component instead of Pure.
    stats_paper = Paper(
        subject_id=subjects["9709"].id,
        component=5,
        variant=1,
        session=ExamSession.MAY_JUNE,
        year=2025,
        total_marks=10,
        level="AS",
    )
    db_session.add(stats_paper)
    db_session.flush()

    question = Question(paper_id=stats_paper.id, question_number=1)
    db_session.add(question)
    db_session.flush()

    sub_part = SubPart(
        question_id=question.id,
        label="",
        max_marks=10,
        topic_id=topics[("9709", "Quadratics")].id,
        sort_order=1,
    )
    db_session.add(sub_part)
    db_session.flush()

    other_attempt = Attempt(
        student_id=student.id,
        paper_id=stats_paper.id,
        status=AttemptStatus.COMPLETED,
        completed_at=start,
    )
    db_session.add(other_attempt)
    db_session.flush()
    db_session.add(
        SubPartResult(attempt_id=other_attempt.id, sub_part_id=sub_part.id, marks_scored=10)
    )
    db_session.commit()

    after = build_family_overview(db_session, student.id, "AS", "Pure")

    assert after.attempts_count == baseline.attempts_count == 5
    assert after.metrics.average_percentage == baseline.metrics.average_percentage
    assert after.trend_points == baseline.trend_points

    stats_overview = build_family_overview(db_session, student.id, "AS", "Statistics")
    assert stats_overview.attempts_count == 1

    a_level_overview = build_family_overview(db_session, student.id, "A", "Pure")
    assert a_level_overview.attempts_count == 0


# --- Calls the trend engine rather than reimplementing it ---


def test_trend_status_matches_trend_engine(db_session):
    subjects, topics, papers = _seed_reference_data(db_session)
    student = _make_student(db_session)
    paper = papers[PAPER_REF]

    start = datetime(2026, 1, 1)
    for i in range(5):
        _record_attempt(db_session, student, paper, start + timedelta(days=7 * i))

    overview = build_family_overview(db_session, student.id, "AS", "Pure")

    assert overview.trend_status == classify_trend(overview.trend_points).status


# --- Metrics: study target / completion / available papers ---


def test_metrics_completion_percentage(db_session):
    subjects, topics, papers = _seed_reference_data(db_session)
    student = _make_student(db_session)
    paper = papers[PAPER_REF]

    start = datetime(2026, 1, 1)
    for i in range(4):
        _record_attempt(db_session, student, paper, start + timedelta(days=7 * i))

    db_session.execute(
        text(
            "INSERT INTO study_targets (student_id, exam_level, component_family, target_value) "
            "VALUES (:sid, 'AS', 'Pure', 8)"
        ),
        {"sid": student.id},
    )
    db_session.commit()

    overview = build_family_overview(db_session, student.id, "AS", "Pure")

    assert overview.metrics.papers_completed == 4
    assert overview.metrics.target_value == 8
    assert overview.metrics.completion_percentage == 50.0
    assert overview.metrics.available_papers == 1


def test_metrics_no_target_set_is_none_not_divide_by_zero(db_session):
    subjects, topics, papers = _seed_reference_data(db_session)
    student = _make_student(db_session)
    paper = papers[PAPER_REF]

    _record_attempt(db_session, student, paper, datetime(2026, 1, 1))

    overview = build_family_overview(db_session, student.id, "AS", "Pure")

    assert overview.metrics.target_value is None
    assert overview.metrics.completion_percentage is None
