"""Tests for the overview assembly layer — the seam between the engines
and the Overview page.

Agent: implement app/services/overview.py per
docs/specs/overview-assembly.md to make these pass.

Per the spec's test contract, these tests cover:
  1. A populated FamilyOverview for a student with >=5 counted Pure AS
     attempts, including a non-empty priorities list when a weak subtopic
     exists.
  2. has_sufficient_data is False with <5, with no fabricated
     weakness/numbers.
  3. Scope isolation: an attempt in another scope never leaks in.
  4. The assembly layer calls the trend engine rather than reimplementing
     it (trend_status must match classify_trend on the same percentages).
  5. The most-recent-attempt-per-paper reduction (planning-performance.md,
     PO decision 2026-09-05): a paper attempted twice contributes ONE
     value — the latest — to every metric, and Papers Completed counts
     distinct papers.

Per docs/specs/subtopic-seed.md, sub_parts point at the most specific
topic level available — a subtopic where the seed data maps one, else the
top-level topic. The weak area used here, "Integration as reverse of
differentiation", is a subtopic under Integration; the assembly layer
derives the topic ("Integration") from the subtopic's parent. It's scored
at 0 marks every attempt against full marks everywhere else.

Because a re-sit no longer adds an observation, the fixtures below build
their history from DISTINCT papers: WEAK_PAPER_REFS are five real AS Pure
papers that all carry the weak subtopic, so it clears the priority
engine's 3-observation gate on distinct papers alone.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select, text

from app.models import Attempt, Paper, Question, Student, SubPart, SubPartResult
from app.models.enums import AttemptStatus, ExamSession
from app.seed.loader import load_papers, load_questions, load_subjects, load_topics
from app.services.overview import build_family_overview
from app.services.trend import classify_trend

WEAK_TOPIC = "Integration as reverse of differentiation"
WEAK_TOPIC_PARENT = "Integration"

# Five distinct AS Pure papers that each map a sub-part to WEAK_TOPIC, in the
# order the fixtures sit them. Their weak-topic marks out of 75 are 4, 3, 4, 4
# and 5, so scoring the weak topic at 0 and everything else at full marks gives
# these exact attempt percentages (v_attempt_totals rounds to 2dp):
WEAK_PAPER_REFS = (
    "9709_11_MJ_2025",  # 71/75 = 94.67
    "9709_12_MJ_2025",  # 72/75 = 96.00
    "9709_13_MJ_2025",  # 71/75 = 94.67
    "9709_15_MJ_2025",  # 71/75 = 94.67
    "9709_11_ON_2025",  # 70/75 = 93.33
)
WEAK_PAPER_PERCENTAGES = (94.67, 96.00, 94.67, 94.67, 93.33)
WEAK_PAPER_AVERAGE = 94.67  # mean of the five above, to 2dp

SEEDED_AS_PURE_PAPERS = 9  # app/seed/data/papers.csv


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
    return _record_attempt_scored(db, student, paper, completed_at, _score_sub_part)


def _record_attempt_scored(db, student: Student, paper: Paper, completed_at, score) -> Attempt:
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


def _record_full_marks(db, student: Student, paper: Paper, completed_at: datetime) -> Attempt:
    """A 100% attempt — an exact value to check the reduction against."""
    return _record_attempt_scored(db, student, paper, completed_at, lambda sp: sp.max_marks)


def _record_zero_marks(db, student: Student, paper: Paper, completed_at: datetime) -> Attempt:
    """A 0% attempt — an exact value to check the reduction against."""
    return _record_attempt_scored(db, student, paper, completed_at, lambda sp: 0)


def _record_weak_topic_history(db, student: Student, papers, count: int = 5) -> None:
    """`count` attempts, one on each of the first `count` WEAK_PAPER_REFS."""
    start = datetime(2026, 1, 1)
    for i, ref in enumerate(WEAK_PAPER_REFS[:count]):
        _record_attempt(db, student, papers[ref], start + timedelta(days=7 * i))


# --- Populated panel with a weak subtopic ---


def test_populated_overview_with_sufficient_data(db_session):
    subjects, topics, papers = _seed_reference_data(db_session)
    student = _make_student(db_session)

    _record_weak_topic_history(db_session, student, papers)

    overview = build_family_overview(db_session, student.id, "AS", "Pure")

    assert overview.component_family == "Pure"
    assert overview.exam_level == "AS"
    assert overview.attempts_count == 5
    assert overview.has_sufficient_data is True

    assert overview.predicted_percentage is not None
    assert overview.prediction_confidence == "normal"

    # Five distinct papers, one attempt each.
    assert overview.metrics.papers_completed == 5
    assert overview.trend_points == list(WEAK_PAPER_PERCENTAGES)
    assert overview.metrics.average_percentage == WEAK_PAPER_AVERAGE
    assert overview.metrics.recent_percentage == WEAK_PAPER_PERCENTAGES[-1]

    # WEAK_TOPIC is scored 0 every time against full marks elsewhere, so
    # it's the only subtopic with a qualifying gap.
    assert len(overview.priorities) == 1
    assert overview.priorities[0].subtopic == WEAK_TOPIC
    assert overview.priorities[0].topic == WEAK_TOPIC_PARENT
    assert overview.priorities[0].priority == "High"

    assert overview.insight_rule_id == "INS-02"
    assert overview.insight_text == (
        f"You have made errors in {WEAK_TOPIC} in 4 of your last 4 relevant attempts."
    )
    assert overview.recommendation_rule_id == "REC-02"


# --- Most recent attempt per distinct paper (PO decision 2026-09-05) ---


def test_only_the_most_recent_attempt_per_paper_counts(db_session):
    """A paper attempted twice contributes one value — the latest.

    Three papers, five attempts, exact 0%/100% scores so the arithmetic is
    unambiguous: the superseded attempt is invisible to every metric, in
    both directions (an improvement and a regression).
    """
    subjects, topics, papers = _seed_reference_data(db_session)
    student = _make_student(db_session)
    start = datetime(2026, 1, 1)

    first, second, third = (papers[ref] for ref in WEAK_PAPER_REFS[:3])

    # Paper one: a failed attempt, then a re-sit at full marks -> 100.
    _record_zero_marks(db_session, student, first, start)
    _record_full_marks(db_session, student, first, start + timedelta(days=1))
    # Paper two: full marks, then a worse re-sit -> 0. The latest wins even
    # when it is the weaker of the two.
    _record_full_marks(db_session, student, second, start + timedelta(days=2))
    _record_zero_marks(db_session, student, second, start + timedelta(days=3))
    # Paper three: attempted once.
    _record_full_marks(db_session, student, third, start + timedelta(days=4))

    overview = build_family_overview(db_session, student.id, "AS", "Pure")

    assert overview.metrics.papers_completed == 3
    assert overview.attempts_count == 3  # five attempts, three counted
    assert overview.trend_points == [100.0, 0.0, 100.0]
    assert overview.metrics.average_percentage == 66.67  # not (0+100+100+0+100)/5
    assert overview.metrics.recent_percentage == 100.0


def test_repeat_attempts_do_not_reach_the_sufficient_data_gate(db_session):
    """Five attempts at one paper is one observation, not five.

    Insufficient data is never manufactured by re-sitting the same paper —
    the >=5 gate counts distinct papers now that the engines do.
    """
    subjects, topics, papers = _seed_reference_data(db_session)
    student = _make_student(db_session)
    paper = papers[WEAK_PAPER_REFS[0]]

    start = datetime(2026, 1, 1)
    for i in range(5):
        _record_attempt(db_session, student, paper, start + timedelta(days=7 * i))

    overview = build_family_overview(db_session, student.id, "AS", "Pure")

    assert overview.metrics.papers_completed == 1
    assert overview.attempts_count == 1
    assert overview.has_sufficient_data is False
    assert overview.trend_status == "More data needed"
    assert overview.priorities == []  # one observation, below the engine's 3


def test_repeat_attempts_do_not_reach_the_priority_observation_gate(db_session):
    """A subtopic seen in 2 papers stays below the gate however often those
    two papers are re-attempted; a third distinct paper clears it."""
    subjects, topics, papers = _seed_reference_data(db_session)
    student = _make_student(db_session)
    start = datetime(2026, 1, 1)

    # Two papers carrying the weak subtopic, re-sat three times each, plus the
    # only two seeded AS Pure papers that do not carry it at all.
    two_weak = [papers[ref] for ref in WEAK_PAPER_REFS[:2]]
    no_weak = [papers["9709_13_ON_2025"], papers["9709_15_ON_2025"]]

    day = 0
    for paper in two_weak:
        for _ in range(3):  # re-sat three times each: still 2 observations
            _record_attempt(db_session, student, paper, start + timedelta(days=day))
            day += 1
    for paper in no_weak:
        _record_attempt(db_session, student, paper, start + timedelta(days=day))
        day += 1

    overview = build_family_overview(db_session, student.id, "AS", "Pure")
    assert overview.attempts_count == 4  # eight attempts, four papers
    assert [p.subtopic for p in overview.priorities] == []

    # A third DISTINCT paper carrying the weak subtopic clears the gate.
    _record_attempt(db_session, student, papers[WEAK_PAPER_REFS[2]], start + timedelta(days=day))
    overview = build_family_overview(db_session, student.id, "AS", "Pure")

    assert overview.attempts_count == 5
    assert [p.subtopic for p in overview.priorities] == [WEAK_TOPIC]


# --- Insufficient data: no fabricated weakness or numbers ---


def test_insufficient_data_below_five_attempts(db_session):
    subjects, topics, papers = _seed_reference_data(db_session)
    student = _make_student(db_session)

    _record_weak_topic_history(db_session, student, papers, count=2)

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

    _record_weak_topic_history(db_session, student, papers)

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
        completed_at=datetime(2026, 1, 1),
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

    _record_weak_topic_history(db_session, student, papers)

    overview = build_family_overview(db_session, student.id, "AS", "Pure")

    assert overview.trend_status == classify_trend(overview.trend_points).status


# --- Metrics: study target / completion / available papers ---


def test_metrics_completion_percentage(db_session):
    subjects, topics, papers = _seed_reference_data(db_session)
    student = _make_student(db_session)

    _record_weak_topic_history(db_session, student, papers, count=4)

    db_session.execute(
        text(
            "INSERT INTO study_targets (student_id, exam_level, component_family, target_value) "
            "VALUES (:sid, 'AS', 'Pure', 8)"
        ),
        {"sid": student.id},
    )
    db_session.commit()

    overview = build_family_overview(db_session, student.id, "AS", "Pure")

    # 4 distinct papers completed against a target of 8.
    assert overview.metrics.papers_completed == 4
    assert overview.metrics.target_value == 8
    assert overview.metrics.completion_percentage == 50.0
    assert overview.metrics.available_papers == SEEDED_AS_PURE_PAPERS


def test_papers_completed_counts_distinct_papers_not_attempts(db_session):
    """OV-T-003b — Papers Completed counts distinct papers, and completion
    can never be inflated by re-attempting one paper."""
    subjects, topics, papers = _seed_reference_data(db_session)
    student = _make_student(db_session)
    paper_one = papers[WEAK_PAPER_REFS[0]]
    paper_two = papers[WEAK_PAPER_REFS[1]]

    start = datetime(2026, 1, 1)
    _record_attempt(db_session, student, paper_one, start)
    _record_attempt(db_session, student, paper_one, start + timedelta(days=7))
    _record_attempt(db_session, student, paper_two, start + timedelta(days=14))

    db_session.execute(
        text(
            "INSERT INTO study_targets (student_id, exam_level, component_family, target_value) "
            "VALUES (:sid, 'AS', 'Pure', 4)"
        ),
        {"sid": student.id},
    )
    db_session.commit()

    overview = build_family_overview(db_session, student.id, "AS", "Pure")

    # Two distinct papers out of three attempts.
    assert overview.metrics.papers_completed == 2
    assert overview.metrics.completion_percentage == 50.0

    # The counted series matches: one value per paper, not one per attempt.
    assert overview.attempts_count == 2
    assert len(overview.trend_points) == 2


def test_metrics_no_target_set_is_none_not_divide_by_zero(db_session):
    subjects, topics, papers = _seed_reference_data(db_session)
    student = _make_student(db_session)

    _record_attempt(db_session, student, papers[WEAK_PAPER_REFS[0]], datetime(2026, 1, 1))

    overview = build_family_overview(db_session, student.id, "AS", "Pure")

    assert overview.metrics.target_value is None
    assert overview.metrics.completion_percentage is None
