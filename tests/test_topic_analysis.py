"""Tests for the Topic Analysis service (docs/specs/topic-analysis-service.md).

Topic Analysis is read-only and reuses Overview's data and calculation
definitions — it introduces no new formulas. These tests cover the spec's
test contract:

  - 8 topics returned, syllabus-ordered, for AS Pure.
  - The priority topic is the default selected topic.
  - The weakest eligible subtopic (lowest avg, >= 3 obs) is default-selected.
  - The question list contains only marks_lost > 0 rows, sorted descending.
  - Variant display composes correctly (component 1, variant 2 -> "12").
  - Scope isolation: A-level / Statistics attempts never leak into an AS Pure view.
  - A subtopic with < 3 observations shows "Insufficient data", not a weakness.
  - Average Performance matches Overview's value for the same scope.

The fixtures mirror tests/test_overview_assembly.py: the deliberately weak area
"Integration as reverse of differentiation" (a subtopic under Integration) is
scored 0 every attempt against full marks everywhere else, on five distinct AS
Pure papers, so it clears the priority engine's gates on distinct papers alone
and makes Integration the priority topic.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select

from app.models import Attempt, Paper, Question, Student, SubPart, SubPartResult, Topic
from app.models.enums import AttemptStatus, ExamSession
from app.seed.loader import load_papers, load_questions, load_subjects, load_topics
from app.services.overview import build_family_overview
from app.services.paper_catalog import variant_display
from app.services.topic_analysis import build_topic_analysis

WEAK_TOPIC = "Integration as reverse of differentiation"
WEAK_TOPIC_PARENT = "Integration"

# Five distinct AS Pure papers that each map ONE sub-part to WEAK_TOPIC. Scoring
# that sub-part 0 and everything else full loses 4, 3, 4, 4 and 5 marks — so the
# WEAK_TOPIC lost-mark list, sorted descending, is [5, 4, 4, 4, 3].
WEAK_PAPER_REFS = (
    "9709_11_MJ_2025",  # lost 4, variant 1
    "9709_12_MJ_2025",  # lost 3, variant 2
    "9709_13_MJ_2025",  # lost 4, variant 3
    "9709_15_MJ_2025",  # lost 4, variant 5
    "9709_11_ON_2025",  # lost 5, variant 1
)

EIGHT_PURE_TOPICS_IN_ORDER = [
    "Quadratics",
    "Functions",
    "Coordinate Geometry",
    "Circular Measure",
    "Trigonometry",
    "Series",
    "Differentiation",
    "Integration",
]


def _seed_reference_data(db):
    subjects = load_subjects(db)
    topics = load_topics(db, subjects)
    papers = load_papers(db, subjects)
    load_questions(db, papers, topics)
    db.commit()
    return subjects, topics, papers


def _make_student(db) -> Student:
    student = Student(
        username="topic_analysis_test_student",
        display_name="Test Student",
        level="AS",
        password_hash="not-a-real-hash",
    )
    db.add(student)
    db.flush()
    return student


def _score_sub_part(sub_part: SubPart) -> int:
    """Full marks everywhere except the deliberately weak subtopic."""
    if sub_part.topic.name == WEAK_TOPIC:
        return 0
    return sub_part.max_marks


def _record_attempt(db, student, paper, completed_at, score=_score_sub_part) -> Attempt:
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
        db.add(SubPartResult(attempt_id=attempt.id, sub_part_id=sp.id, marks_scored=score(sp)))
    db.commit()
    return attempt


def _record_weak_history(db, student, papers, count: int = 5) -> None:
    start = datetime(2026, 1, 1)
    for i, ref in enumerate(WEAK_PAPER_REFS[:count]):
        _record_attempt(db, student, papers[ref], start + timedelta(days=7 * i))


def _topic_id(db, name: str) -> int:
    return db.scalar(select(Topic.id).where(Topic.name == name, Topic.parent_id.is_(None)))


# --- Variant display (unit, against the BRD examples) ------------------------


def test_variant_display_composes_component_and_variant():
    # component 1, variant 2 -> "12" (component * 10 + variant), per the spec.
    assert variant_display(1, 2) == "12"
    assert variant_display(1, 1) == "11"
    assert variant_display(1, 3) == "13"
    assert variant_display(3, 2) == "32"


# --- Topic table: all 8, syllabus order -------------------------------------


def test_returns_eight_pure_topics_in_syllabus_order(db_session):
    _, _, papers = _seed_reference_data(db_session)
    student = _make_student(db_session)
    _record_weak_history(db_session, student, papers)

    view = build_topic_analysis(db_session, student.id, "AS", "Pure")

    assert [t.topic_name for t in view.topics] == EIGHT_PURE_TOPICS_IN_ORDER


# --- Priority topic is the default selected topic ---------------------------


def test_priority_topic_is_default_selected_topic(db_session):
    _, _, papers = _seed_reference_data(db_session)
    student = _make_student(db_session)
    _record_weak_history(db_session, student, papers)

    view = build_topic_analysis(db_session, student.id, "AS", "Pure")

    integration_id = _topic_id(db_session, WEAK_TOPIC_PARENT)
    assert view.summary.priority_topic_name == WEAK_TOPIC_PARENT
    assert view.selected_topic_id == integration_id


def test_a_passed_selected_topic_overrides_the_priority_default(db_session):
    _, _, papers = _seed_reference_data(db_session)
    student = _make_student(db_session)
    _record_weak_history(db_session, student, papers)

    quadratics_id = _topic_id(db_session, "Quadratics")
    view = build_topic_analysis(
        db_session, student.id, "AS", "Pure", selected_topic_id=quadratics_id
    )

    # Selection overrides the default; the priority TILE still names Integration.
    assert view.selected_topic_id == quadratics_id
    assert view.summary.priority_topic_name == WEAK_TOPIC_PARENT
    assert {s.subtopic_name for s in view.subtopics}  # Quadratics has subtopics


# --- Weakest eligible subtopic is default-selected --------------------------


def test_weakest_eligible_subtopic_is_default_selected(db_session):
    _, _, papers = _seed_reference_data(db_session)
    student = _make_student(db_session)
    _record_weak_history(db_session, student, papers)

    view = build_topic_analysis(db_session, student.id, "AS", "Pure")

    # Under Integration the weak subtopic has 5 observations at 0% — lower than
    # any other eligible (>= 3 obs) subtopic, so it defaults.
    weak_id = db_session.scalar(select(Topic.id).where(Topic.name == WEAK_TOPIC))
    assert view.selected_subtopic_id == weak_id
    selected = next(s for s in view.subtopics if s.subtopic_id == weak_id)
    assert selected.subtopic_name == WEAK_TOPIC
    assert selected.status == "High Priority"


# --- Question-level lost-mark list ------------------------------------------


def test_lost_mark_list_only_positive_losses_sorted_descending(db_session):
    _, _, papers = _seed_reference_data(db_session)
    student = _make_student(db_session)
    _record_weak_history(db_session, student, papers)

    view = build_topic_analysis(db_session, student.id, "AS", "Pure")

    losses = view.lost_mark_questions
    # Five weak papers, one weak sub-part each, all scored 0 -> five lost-mark rows.
    assert [q.marks_lost for q in losses] == [5, 4, 4, 4, 3]
    assert all(q.marks_lost > 0 for q in losses)
    assert all(q.your_score == 0 for q in losses)
    assert all(q.max_marks == q.marks_lost for q in losses)
    # Every weak sub-part is on a component-1 paper, variants 1/2/3/5.
    assert all(q.variant_display in {"11", "12", "13", "15"} for q in losses)


def test_empty_question_panel_when_subtopic_has_no_lost_marks(db_session):
    _, _, papers = _seed_reference_data(db_session)
    student = _make_student(db_session)
    _record_weak_history(db_session, student, papers)

    # "Area under a curve & line" is scored full every time -> no marks lost.
    strong_subtopic_id = db_session.scalar(
        select(Topic.id).where(Topic.name == "Area under a curve & line")
    )
    view = build_topic_analysis(
        db_session,
        student.id,
        "AS",
        "Pure",
        selected_subtopic_id=strong_subtopic_id,
    )

    assert view.selected_subtopic_id == strong_subtopic_id
    assert view.lost_mark_questions == []


# --- Insufficient data (subtopic below the 3-observation gate) ---------------


def test_subtopic_below_three_observations_is_insufficient(db_session):
    _, _, papers = _seed_reference_data(db_session)
    student = _make_student(db_session)
    _record_weak_history(db_session, student, papers)

    view = build_topic_analysis(db_session, student.id, "AS", "Pure")
    by_name = {s.subtopic_name: s for s in view.subtopics}

    # These Integration subtopics appear in only 1 and 2 of the five papers.
    assert by_name["Definite & indefinite integration"].status == "Insufficient data"
    assert by_name["Integration with volume"].status == "Insufficient data"
    # A subtopic that was never attempted still appears, as Insufficient data.
    assert by_name["Constant of integration"].status == "Insufficient data"
    assert by_name["Constant of integration"].questions == 0


def test_below_reliability_gate_statuses_are_insufficient_but_facts_show(db_session):
    _, _, papers = _seed_reference_data(db_session)
    student = _make_student(db_session)
    _record_weak_history(db_session, student, papers, count=3)  # < 5 papers

    view = build_topic_analysis(db_session, student.id, "AS", "Pure")

    assert view.summary.papers_attempted == 3
    # Basic facts still show; every reliability-dependent status collapses.
    assert view.summary.average_performance is not None
    assert all(t.status == "Insufficient data" for t in view.topics)


# --- Average Performance matches Overview (one source of truth) --------------


def test_average_performance_matches_overview(db_session):
    _, _, papers = _seed_reference_data(db_session)
    student = _make_student(db_session)
    _record_weak_history(db_session, student, papers)

    view = build_topic_analysis(db_session, student.id, "AS", "Pure")
    overview = build_family_overview(db_session, student.id, "AS", "Pure")

    assert view.summary.average_performance == overview.metrics.average_percentage
    assert view.summary.papers_attempted == overview.metrics.papers_completed
    assert view.summary.papers_available == overview.metrics.available_papers


def test_questions_analysed_equals_sum_of_topic_questions(db_session):
    _, _, papers = _seed_reference_data(db_session)
    student = _make_student(db_session)
    _record_weak_history(db_session, student, papers)

    view = build_topic_analysis(db_session, student.id, "AS", "Pure")

    assert view.summary.questions_analysed == sum(t.questions for t in view.topics)
    assert view.summary.questions_analysed > 0


# --- Scope isolation --------------------------------------------------------


def test_scope_isolation_other_family_and_level_do_not_leak(db_session):
    subjects, topics, papers = _seed_reference_data(db_session)
    student = _make_student(db_session)
    _record_weak_history(db_session, student, papers)

    baseline = build_topic_analysis(db_session, student.id, "AS", "Pure")

    # A completed attempt in another scope: same subject, a Statistics component,
    # plus an A-level Pure paper. Neither may touch the AS Pure view.
    stats_paper = Paper(
        subject_id=subjects["9709"].id,
        component=5,
        variant=1,
        session=ExamSession.MAY_JUNE,
        year=2025,
        total_marks=10,
        level="AS",
    )
    a_level_paper = Paper(
        subject_id=subjects["9709"].id,
        component=3,
        variant=1,
        session=ExamSession.MAY_JUNE,
        year=2025,
        total_marks=10,
        level="A",
    )
    db_session.add_all([stats_paper, a_level_paper])
    db_session.flush()

    for paper in (stats_paper, a_level_paper):
        question = Question(paper_id=paper.id, question_number=1)
        db_session.add(question)
        db_session.flush()
        sub_part = SubPart(
            question_id=question.id,
            label="",
            max_marks=10,
            topic_id=topics[("9709", "Discriminants")].id,
            sort_order=1,
        )
        db_session.add(sub_part)
        db_session.flush()
        attempt = Attempt(
            student_id=student.id,
            paper_id=paper.id,
            status=AttemptStatus.COMPLETED,
            completed_at=datetime(2026, 2, 1),
        )
        db_session.add(attempt)
        db_session.flush()
        db_session.add(
            SubPartResult(attempt_id=attempt.id, sub_part_id=sub_part.id, marks_scored=0)
        )
    db_session.commit()

    after = build_topic_analysis(db_session, student.id, "AS", "Pure")

    assert [t.topic_name for t in after.topics] == [t.topic_name for t in baseline.topics]
    assert after.summary.questions_analysed == baseline.summary.questions_analysed
    assert after.summary.average_performance == baseline.summary.average_performance
    assert after.summary.papers_attempted == baseline.summary.papers_attempted
    assert after.selected_topic_id == baseline.selected_topic_id
    assert [q.marks_lost for q in after.lost_mark_questions] == [
        q.marks_lost for q in baseline.lost_mark_questions
    ]


def test_statistics_view_is_isolated_from_pure_attempts(db_session):
    _, _, papers = _seed_reference_data(db_session)
    student = _make_student(db_session)
    _record_weak_history(db_session, student, papers)

    stats_view = build_topic_analysis(db_session, student.id, "AS", "Statistics")

    # No Statistics papers or attempts exist, so nothing is analysed.
    assert stats_view.summary.questions_analysed == 0
    assert stats_view.summary.papers_attempted == 0
    assert stats_view.lost_mark_questions == []
