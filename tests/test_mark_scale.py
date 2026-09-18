"""Tests for the mark-scale source — docs/specs/mark-scale.md.

Covers:
  1. get_family_total_marks reads the total from papers in scope via
     component_families, never hard-coding 75.
  2. FamilyOverview's mark-scale fields (total_marks, average/recent as
     marks, predicted mark range) are derived in the assembly layer from
     the existing percentages, scaled by whatever total the scope's
     papers actually carry — including a family whose total is 60, to
     prove the 75 from the Pure family isn't leaking in.
  3. Empty-scope / no-papers cases return None rather than fabricating a
     denominator, per the spec's "What NOT to do".

Reuses the seeding helpers from test_overview_assembly.py's fixtures
(same reference data, same student/attempt shape) — including its
DISTINCT-paper history, since only the most recent attempt at a paper
counts (planning-performance.md, PO decision 2026-09-05).
"""

from __future__ import annotations

from datetime import datetime, timedelta

from app.models import Attempt, Paper, Question, Student, SubPart, SubPartResult
from app.models.enums import AttemptStatus, ExamSession
from app.seed.loader import load_papers, load_questions, load_subjects, load_topics
from app.services.overview import (
    PREDICTED_RANGE_MARGIN_PP,
    _percentage_to_marks,
    _predicted_marks_range,
    build_family_overview,
    get_family_total_marks,
)


def _seed_reference_data(db):
    subjects = load_subjects(db)
    topics = load_topics(db, subjects)
    papers = load_papers(db, subjects)
    load_questions(db, papers, topics)
    db.commit()
    return subjects, topics, papers


def _make_student(db) -> Student:
    student = Student(
        username="mark_scale_test_student",
        display_name="Test Student",
        level="AS",
        password_hash="not-a-real-hash",
    )
    db.add(student)
    db.flush()
    return student


PURE_WEAK_TOPIC = "Integration as reverse of differentiation"

# The same five distinct AS Pure papers test_overview_assembly.py uses, in the
# same order — scoring PURE_WEAK_TOPIC at 0 and everything else at full marks
# gives 94.67, 96.00, 94.67, 94.67 and 93.33, averaging 94.67 of 75 marks.
PURE_PAPER_REFS = (
    "9709_11_MJ_2025",
    "9709_12_MJ_2025",
    "9709_13_MJ_2025",
    "9709_15_MJ_2025",
    "9709_11_ON_2025",
)
PURE_AVERAGE_PERCENTAGE = 94.67
PURE_RECENT_PERCENTAGE = 93.33


def _record_pure_attempt(db, student, paper, completed_at):
    """Full marks everywhere except PURE_WEAK_TOPIC.

    Same scoring shape as test_overview_assembly.py's fixture, so the
    resulting percentages are exact rather than order-dependent.
    """
    from sqlalchemy import select

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
        scored = 0 if sp.topic.name == PURE_WEAK_TOPIC else sp.max_marks
        db.add(SubPartResult(attempt_id=attempt.id, sub_part_id=sp.id, marks_scored=scored))
    db.commit()
    return attempt


def _record_pure_attempt_scored(db, student, paper, completed_at, score):
    """One completed attempt scoring every sub-part through `score`."""
    from sqlalchemy import select

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


def _record_full_marks(db, student, paper, completed_at):
    return _record_pure_attempt_scored(db, student, paper, completed_at, lambda sp: sp.max_marks)


def _record_zero_marks(db, student, paper, completed_at):
    return _record_pure_attempt_scored(db, student, paper, completed_at, lambda sp: 0)


def _seed_statistics_paper(db, subjects, topics, variant: int = 1):
    """A Statistics paper (component 5) whose total is 60, not 75 — the
    contract's proof that get_family_total_marks isn't hard-coded.

    `variant` distinguishes papers so a caller can seed several DISTINCT
    ones; a paper is subject + component + variant + session + year.
    """
    paper = Paper(
        subject_id=subjects["9709"].id,
        component=5,
        variant=variant,
        session=ExamSession.MAY_JUNE,
        year=2025,
        total_marks=60,
        level="AS",
    )
    db.add(paper)
    db.flush()

    question = Question(paper_id=paper.id, question_number=1)
    db.add(question)
    db.flush()

    sub_part = SubPart(
        question_id=question.id,
        label="",
        max_marks=25,
        topic_id=topics[("9709", "Quadratics")].id,
        sort_order=1,
    )
    db.add(sub_part)
    db.flush()
    db.commit()
    return paper, sub_part


def _record_stats_attempt_at_88_percent(db, student, paper, sub_part, completed_at):
    """22/25 = 88% on one Statistics paper, whose family total is 60."""
    attempt = Attempt(
        student_id=student.id,
        paper_id=paper.id,
        status=AttemptStatus.COMPLETED,
        completed_at=completed_at,
    )
    db.add(attempt)
    db.flush()
    db.add(SubPartResult(attempt_id=attempt.id, sub_part_id=sub_part.id, marks_scored=22))
    db.commit()
    return attempt


# --- get_family_total_marks: reads from papers, never hard-coded ---


def test_get_family_total_marks_reads_seeded_pure_total(db_session):
    subjects, topics, papers = _seed_reference_data(db_session)

    total = get_family_total_marks(db_session, "AS", "Pure")

    assert total == 75


def test_get_family_total_marks_uses_seeded_total_not_75(db_session):
    """A family whose papers total 60 must return 60 — proves the value is
    read from papers.total_marks, not hard-coded to the Pure family's 75."""
    subjects, topics, papers = _seed_reference_data(db_session)
    _seed_statistics_paper(db_session, subjects, topics)

    stats_total = get_family_total_marks(db_session, "AS", "Statistics")
    pure_total = get_family_total_marks(db_session, "AS", "Pure")

    assert stats_total == 60
    assert pure_total == 75


def test_get_family_total_marks_returns_none_when_no_papers_in_scope(db_session):
    _seed_reference_data(db_session)  # only seeds an AS Pure paper

    total = get_family_total_marks(db_session, "A", "Pure")

    assert total is None


# --- pure conversion helpers: percentage -> marks, predicted range ---


def test_percentage_to_marks_matches_spec_example():
    # docs/specs/mark-scale.md test contract: 77.9% of a 75-mark total.
    assert _percentage_to_marks(77.9, 75) == 58.4


def test_percentage_to_marks_none_when_either_input_missing():
    assert _percentage_to_marks(None, 75) is None
    assert _percentage_to_marks(88.0, None) is None


def test_predicted_marks_range_matches_spec_example():
    # docs/specs/mark-scale.md test contract: 88% predicted, total 75,
    # +/-3pp -> approx 63.8 - 68.3 / 75.
    low, high = _predicted_marks_range(88.0, 75)

    assert low == 63.8
    assert high == 68.2 or high == 68.3  # float-boundary rounding of 68.25


def test_predicted_marks_range_clamps_to_total_marks():
    low, high = _predicted_marks_range(99.0, 75)
    assert high == 75.0  # 99 + 3pp would exceed 100%, clamped at the total

    low, high = _predicted_marks_range(1.0, 75)
    assert low == 0.0  # 1 - 3pp would go negative, clamped at 0

    assert PREDICTED_RANGE_MARGIN_PP == 3.0


def test_predicted_marks_range_none_when_no_prediction_or_no_total():
    assert _predicted_marks_range(None, 75) == (None, None)
    assert _predicted_marks_range(88.0, None) == (None, None)


# --- FamilyOverview: mark-scale fields end to end ---


def test_family_overview_marks_fields_for_pure(db_session):
    subjects, topics, papers = _seed_reference_data(db_session)
    student = _make_student(db_session)

    start = datetime(2026, 1, 1)
    for i, ref in enumerate(PURE_PAPER_REFS):
        _record_pure_attempt(db_session, student, papers[ref], start + timedelta(days=7 * i))

    overview = build_family_overview(db_session, student.id, "AS", "Pure")

    assert overview.metrics.average_percentage == PURE_AVERAGE_PERCENTAGE
    assert overview.metrics.recent_percentage == PURE_RECENT_PERCENTAGE
    assert overview.total_marks == 75
    assert overview.average_score_marks == 71.0  # 94.67% of 75
    assert overview.recent_score_marks == 70.0  # 93.33% of 75

    # The mark range is the engine's percentage scaled by the family total,
    # +/- PREDICTED_RANGE_MARGIN_PP — not a second prediction.
    predicted = overview.predicted_percentage
    assert predicted is not None
    assert overview.predicted_marks_low == _percentage_to_marks(predicted - 3.0, 75)
    assert overview.predicted_marks_high == _percentage_to_marks(predicted + 3.0, 75)


def test_family_overview_marks_ignore_superseded_attempts(db_session):
    """A re-sit replaces its paper's earlier attempt in the mark figures too.

    Full marks on every paper, then one paper re-sat at zero: the average
    must fall to the four-of-five level, proving the marks fields are scaled
    from the reduced series and not from every attempt ever saved.
    """
    subjects, topics, papers = _seed_reference_data(db_session)
    student = _make_student(db_session)

    start = datetime(2026, 1, 1)
    for i, ref in enumerate(PURE_PAPER_REFS):
        _record_full_marks(db_session, student, papers[ref], start + timedelta(days=7 * i))

    _record_zero_marks(db_session, student, papers[PURE_PAPER_REFS[0]], start + timedelta(days=60))

    overview = build_family_overview(db_session, student.id, "AS", "Pure")

    assert overview.attempts_count == 5
    assert overview.metrics.average_percentage == 80.0  # (0 + 100*4) / 5
    assert overview.total_marks == 75
    assert overview.average_score_marks == 60.0  # 80% of 75
    assert overview.recent_score_marks == 0.0  # the re-sit is the latest


def test_family_overview_marks_scaled_to_family_total_not_75(db_session):
    """Same 88% average as the Pure test, but this family's papers total
    60 — average_score_marks must come out at 52.8, not the Pure 66.0,
    proving the scale isn't hard-coded to 75."""
    subjects, topics, papers = _seed_reference_data(db_session)
    student = _make_student(db_session)

    # Five DISTINCT Statistics papers — one attempt each, since a re-sit of
    # one paper would collapse to a single counted attempt.
    start = datetime(2026, 1, 1)
    for i in range(5):
        stats_paper, sub_part = _seed_statistics_paper(db_session, subjects, topics, variant=i + 1)
        _record_stats_attempt_at_88_percent(
            db_session, student, stats_paper, sub_part, start + timedelta(days=7 * i)
        )

    overview = build_family_overview(db_session, student.id, "AS", "Statistics")

    assert overview.metrics.average_percentage == 88.0
    assert overview.total_marks == 60
    assert overview.average_score_marks == 52.8
    assert overview.average_score_marks != 66.0


def test_family_overview_marks_none_when_scope_has_no_papers(db_session):
    _seed_reference_data(db_session)
    student = _make_student(db_session)

    # A-level Pure: no A-level papers are seeded, so there's no total to
    # scale against — the spec forbids fabricating one.
    overview = build_family_overview(db_session, student.id, "A", "Pure")

    assert overview.total_marks is None
    assert overview.average_score_marks is None
    assert overview.recent_score_marks is None
    assert overview.predicted_marks_low is None
    assert overview.predicted_marks_high is None


def test_family_overview_marks_none_when_no_attempts_yet(db_session):
    _seed_reference_data(db_session)
    student = _make_student(db_session)

    # Papers exist in scope (so total_marks resolves), but the student has
    # no attempts yet — the marks fields that depend on a percentage must
    # stay None rather than showing "0".
    overview = build_family_overview(db_session, student.id, "AS", "Pure")

    assert overview.total_marks == 75
    assert overview.average_score_marks is None
    assert overview.recent_score_marks is None
    assert overview.predicted_marks_low is None
    assert overview.predicted_marks_high is None
