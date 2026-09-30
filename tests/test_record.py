"""Record Practice Paper write path — docs/specs/record-service.md.

The contract in that spec, test by test:

  * RP-T-011 — entries summing to 7 marks lost score 68/75 (90.7%), and the
    analytics view agrees with the figure the service returned.
  * THE CONVERSION — max 5, marks_lost 2 stores marks_scored 3.
  * RP-V-001/004/005/006/007/008/009/010/011 — each rejected, and all of them
    reported TOGETHER rather than first-fail.
  * RP-F-001 — create makes exactly one attempt.
  * RP-F-006 / RP-T-015 — edit updates in place; the completed count is unchanged.
  * §19 — an edit of someone else's attempt is refused.

Every submission covers all 22 sub-parts of the paper, because the form has a
row per sub-part and a missing row is a blank one (RP-V-004). `_entries` builds
that full set at "No Error, nothing lost" and takes per-row overrides, which is
also how the real form arrives: mostly zeros, a few losses.
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import func, select, text

from app.models import Attempt, Paper, Question, Student, SubPart, SubPartResult
from app.models.enums import AttemptStatus, ExamSession
from app.seed.loader import load_papers, load_questions, load_subjects, load_topics
from app.services.record import (
    ERROR_TYPES,
    FAULT_ERROR_TYPES,
    NO_ERROR,
    AttemptNotFoundError,
    RecordValidationError,
    SubPartEntry,
    save_attempt,
)

PAPER_REF = "9709_11_MJ_2025"
PAPER_TOTAL = 75  # app/seed/data/questions.csv — 22 sub-parts summing to 75
SUB_PART_COUNT = 22
DATE_COMPLETED = date(2026, 9, 20)


# --- fixtures ---------------------------------------------------------------


def _seed_reference_data(db):
    subjects = load_subjects(db)
    topics = load_topics(db, subjects)
    papers = load_papers(db, subjects)
    load_questions(db, papers, topics)
    db.commit()
    return subjects, topics, papers


def _make_student(db, username: str = "record_test_student") -> Student:
    student = Student(
        username=username,
        display_name="Test Student",
        level="AS",
        password_hash="not-a-real-hash",
    )
    db.add(student)
    db.commit()
    return student


def _sub_parts(db, paper: Paper) -> list[SubPart]:
    """The paper's sub-parts in form order — the order the page renders rows."""
    return list(
        db.scalars(
            select(SubPart)
            .join(SubPart.question)
            .where(SubPart.question.has(paper_id=paper.id))
            .order_by(SubPart.sort_order, SubPart.id)
        ).all()
    )


def _entries(
    db,
    paper: Paper,
    losses: dict[int, tuple[object, str]] | None = None,
) -> list[SubPartEntry]:
    """A complete, valid submission, with `losses` overriding rows by INDEX.

    Indexes rather than sub_part_ids so a test can say "the third row lost 2
    marks" without knowing what ids the database assigned.
    """
    losses = losses or {}
    rows = _sub_parts(db, paper)
    entries = []
    for index, sub_part in enumerate(rows):
        marks_lost, error_type = losses.get(index, (0, NO_ERROR))
        entries.append(
            SubPartEntry(sub_part_id=sub_part.id, marks_lost=marks_lost, error_type=error_type)
        )
    return entries


# app/seed/data/papers.csv's paper_ref codes: 9709_<component><variant>_<session>_<year>
SESSIONS = {"MJ": ExamSession.MAY_JUNE, "ON": ExamSession.OCT_NOV, "FM": ExamSession.MARCH}


def _paper(db, paper_ref: str = PAPER_REF) -> Paper:
    """The seeded Paper for a papers.csv paper_ref.

    Session is part of the lookup: 9709_11_MJ_2025 and 9709_11_ON_2025 share a
    component and variant and differ only by session.
    """
    _subject, component_variant, session, year = paper_ref.split("_")
    return db.scalar(
        select(Paper).where(
            Paper.component == int(component_variant[0]),
            Paper.variant == int(component_variant[1]),
            Paper.session == SESSIONS[session],
            Paper.year == int(year),
        )
    )


@pytest.fixture
def paper(db_session) -> Paper:
    _seed_reference_data(db_session)
    paper = _paper(db_session)
    assert paper is not None, "seed data missing " + PAPER_REF
    return paper


@pytest.fixture
def student(db_session) -> Student:
    return _make_student(db_session)


def _completed_count(db, student: Student) -> int:
    return db.scalar(
        select(func.count())
        .select_from(Attempt)
        .where(Attempt.student_id == student.id, Attempt.status == AttemptStatus.COMPLETED)
    )


def _result_for(db, attempt_id: int, sub_part_id: int) -> SubPartResult:
    return db.scalar(
        select(SubPartResult).where(
            SubPartResult.attempt_id == attempt_id,
            SubPartResult.sub_part_id == sub_part_id,
        )
    )


# --- the nine controlled error types (§8) -----------------------------------


def test_nine_error_types_exactly():
    """§8's controlled list, data driven in one place — not scattered literals."""
    assert ERROR_TYPES == (
        "No Error",
        "Conceptual Error",
        "Calculation Error",
        "Careless Error",
        "Application Error",
        "Misread Question",
        "Incomplete Answer",
        "Time Pressure",
        "Forgot Formula / Rule",
    )
    assert len(ERROR_TYPES) == 9
    assert len(FAULT_ERROR_TYPES) == 8
    assert NO_ERROR not in FAULT_ERROR_TYPES


# --- RP-T-011 and the calculations (§14) ------------------------------------


def test_rp_t_011_seven_marks_lost_scores_68_of_75(db_session, student, paper):
    """RP-T-011: entries summing to 7 marks lost → 68/75, 90.7%."""
    result = save_attempt(
        db_session,
        student_id=student.id,
        paper_id=paper.id,
        date_completed=DATE_COMPLETED,
        entries=_entries(
            db_session,
            paper,
            {
                2: (4, "Conceptual Error"),  # question 2b, max 4
                5: (2, "Careless Error"),  # question 4, max 5
                13: (1, "Time Pressure"),  # question 8, max 8
            },
        ),
    )

    assert result.total_marks == PAPER_TOTAL
    assert result.total_marks_lost == 7
    assert result.total_score == 68
    # 68/75 = 90.666…; carried at 2dp to match v_attempt_totals' ROUND(…, 2),
    # which is the spec's 90.7% once displayed to one place.
    assert result.percentage == pytest.approx(90.67)
    assert round(result.percentage, 1) == 90.7


def test_rp_t_011_analytics_view_agrees(db_session, student, paper):
    """RP-F-007: no recalculate step — the view reports what the service did.

    BRD §32 rule 8 (same metrics everywhere) only holds if the write path and
    v_attempt_totals derive the same score from the same rows.
    """
    result = save_attempt(
        db_session,
        student_id=student.id,
        paper_id=paper.id,
        date_completed=DATE_COMPLETED,
        entries=_entries(db_session, paper, {2: (4, "Conceptual Error"), 5: (3, "Time Pressure")}),
    )

    row = (
        db_session.execute(
            text("""
            SELECT marks_scored, marks_available, percentage, exam_level, component_family
            FROM v_attempt_totals
            WHERE attempt_id = :attempt_id
        """),
            {"attempt_id": result.attempt_id},
        )
        .mappings()
        .one()
    )

    assert row["marks_scored"] == result.total_score == 68
    assert row["marks_available"] == result.total_marks == PAPER_TOTAL
    assert float(row["percentage"]) == pytest.approx(result.percentage)
    assert (row["exam_level"], row["component_family"]) == ("AS", "Pure")


def test_new_attempt_is_the_latest_for_its_paper(db_session, student, paper):
    """completed_at is written, so the counted-attempt view can order it.

    v_latest_paper_attempts sorts `completed_at DESC NULLS LAST`. An attempt
    saved with completed_at NULL would sort OLDEST and every engine would
    ignore the newest result — so the service writes it from date_completed.
    """
    result = save_attempt(
        db_session,
        student_id=student.id,
        paper_id=paper.id,
        date_completed=DATE_COMPLETED,
        entries=_entries(db_session, paper),
    )

    attempt = db_session.get(Attempt, result.attempt_id)
    assert attempt.date_completed == DATE_COMPLETED
    assert attempt.completed_at is not None
    assert attempt.completed_at.date() == DATE_COMPLETED

    latest = db_session.execute(
        text("""
            SELECT attempt_id FROM v_latest_paper_attempts
            WHERE student_id = :student_id AND paper_id = :paper_id
        """),
        {"student_id": student.id, "paper_id": paper.id},
    ).scalar_one()
    assert latest == result.attempt_id


def test_percentage_is_derived_not_stored(db_session, student, paper):
    """§14 rule 14: nothing in the schema holds a total or a percentage."""
    save_attempt(
        db_session,
        student_id=student.id,
        paper_id=paper.id,
        date_completed=DATE_COMPLETED,
        entries=_entries(db_session, paper, {0: (4, "Misread Question")}),
    )
    columns = {c.name for c in Attempt.__table__.columns}
    assert "percentage" not in columns
    assert "total_score" not in columns
    assert "total_marks_lost" not in columns


# --- THE CONVERSION ---------------------------------------------------------


def test_conversion_max_5_lost_2_stores_3(db_session, student, paper):
    """marks_scored = max_marks - marks_lost. Never marks_lost itself."""
    rows = _sub_parts(db_session, paper)
    five_mark_index = next(i for i, sp in enumerate(rows) if sp.max_marks == 5)
    five_mark_sub_part = rows[five_mark_index]
    assert five_mark_sub_part.max_marks == 5

    result = save_attempt(
        db_session,
        student_id=student.id,
        paper_id=paper.id,
        date_completed=DATE_COMPLETED,
        entries=_entries(db_session, paper, {five_mark_index: (2, "Calculation Error")}),
    )

    stored = _result_for(db_session, result.attempt_id, five_mark_sub_part.id)
    assert stored.marks_scored == 3
    assert stored.marks_scored != 2, "marks_lost was stored as marks_scored"
    assert stored.error_type == "Calculation Error"


def test_zero_marks_lost_stores_full_marks(db_session, student, paper):
    """The other end of the conversion: nothing lost means every mark scored."""
    result = save_attempt(
        db_session,
        student_id=student.id,
        paper_id=paper.id,
        date_completed=DATE_COMPLETED,
        entries=_entries(db_session, paper),
    )

    stored = db_session.scalars(
        select(SubPartResult).where(SubPartResult.attempt_id == result.attempt_id)
    ).all()
    assert len(stored) == SUB_PART_COUNT
    by_id = {r.sub_part_id: r for r in stored}
    for sub_part in _sub_parts(db_session, paper):
        assert by_id[sub_part.id].marks_scored == sub_part.max_marks
        assert by_id[sub_part.id].error_type == NO_ERROR
    assert result.total_score == PAPER_TOTAL
    assert result.percentage == pytest.approx(100.0)


def test_full_marks_lost_stores_zero(db_session, student, paper):
    """A whole paper lost stores zeros, not the marks lost, and scores 0%."""
    rows = _sub_parts(db_session, paper)
    losses = {i: (sp.max_marks, "Time Pressure") for i, sp in enumerate(rows)}

    result = save_attempt(
        db_session,
        student_id=student.id,
        paper_id=paper.id,
        date_completed=DATE_COMPLETED,
        entries=_entries(db_session, paper, losses),
    )

    assert result.total_marks_lost == PAPER_TOTAL
    assert result.total_score == 0
    assert result.percentage == pytest.approx(0.0)
    scored = db_session.scalars(
        select(SubPartResult.marks_scored).where(SubPartResult.attempt_id == result.attempt_id)
    ).all()
    assert set(scored) == {0}


# --- Create (RP-F-001) ------------------------------------------------------


def test_create_makes_exactly_one_attempt(db_session, student, paper):
    """RP-F-001: one submission, one attempt, one result row per sub-part."""
    result = save_attempt(
        db_session,
        student_id=student.id,
        paper_id=paper.id,
        date_completed=DATE_COMPLETED,
        entries=_entries(db_session, paper, {1: (2, "Careless Error")}),
    )

    assert _completed_count(db_session, student) == 1
    attempt = db_session.get(Attempt, result.attempt_id)
    assert attempt.status == AttemptStatus.COMPLETED
    assert attempt.paper_id == paper.id
    assert attempt.student_id == student.id
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(SubPartResult)
            .where(SubPartResult.attempt_id == result.attempt_id)
        )
        == SUB_PART_COUNT
    )


def test_two_submissions_are_two_attempts(db_session, student, paper):
    """D5: the same paper may be attempted again — create never upserts."""
    first = save_attempt(
        db_session,
        student_id=student.id,
        paper_id=paper.id,
        date_completed=DATE_COMPLETED,
        entries=_entries(db_session, paper),
    )
    second = save_attempt(
        db_session,
        student_id=student.id,
        paper_id=paper.id,
        date_completed=date(2026, 9, 27),
        entries=_entries(db_session, paper, {0: (4, "Conceptual Error")}),
    )

    assert first.attempt_id != second.attempt_id
    assert _completed_count(db_session, student) == 2


# --- Update (RP-F-005/006, RP-T-015, RP-V-012) ------------------------------


def test_update_edits_in_place_without_duplicating(db_session, student, paper):
    """RP-F-006 / RP-T-015: correcting a paper never adds an attempt."""
    rows = _sub_parts(db_session, paper)
    target_index = next(i for i, sp in enumerate(rows) if sp.max_marks == 5)
    target = rows[target_index]

    created = save_attempt(
        db_session,
        student_id=student.id,
        paper_id=paper.id,
        date_completed=DATE_COMPLETED,
        entries=_entries(db_session, paper, {target_index: (5, "Conceptual Error")}),
    )
    assert created.total_marks_lost == 5

    corrected = save_attempt(
        db_session,
        student_id=student.id,
        paper_id=paper.id,
        date_completed=date(2026, 9, 25),
        entries=_entries(db_session, paper, {target_index: (2, "Calculation Error")}),
        attempt_id=created.attempt_id,
    )

    assert corrected.attempt_id == created.attempt_id
    assert _completed_count(db_session, student) == 1
    assert corrected.total_marks_lost == 2
    assert corrected.total_score == 73

    # Upserted, not re-inserted: still one row per sub-part.
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(SubPartResult)
            .where(SubPartResult.attempt_id == created.attempt_id)
        )
        == SUB_PART_COUNT
    )

    db_session.expire_all()
    stored = _result_for(db_session, created.attempt_id, target.id)
    assert stored.marks_scored == 3
    assert stored.error_type == "Calculation Error"

    attempt = db_session.get(Attempt, created.attempt_id)
    assert attempt.date_completed == date(2026, 9, 25)
    assert attempt.completed_at.date() == date(2026, 9, 25)


def test_update_refuses_another_students_attempt(db_session, student, paper):
    """§19: an attempt that isn't yours cannot be edited, or even confirmed."""
    intruder = _make_student(db_session, username="record_test_intruder")
    created = save_attempt(
        db_session,
        student_id=student.id,
        paper_id=paper.id,
        date_completed=DATE_COMPLETED,
        entries=_entries(db_session, paper, {0: (4, "Careless Error")}),
    )

    with pytest.raises(AttemptNotFoundError):
        save_attempt(
            db_session,
            student_id=intruder.id,
            paper_id=paper.id,
            date_completed=DATE_COMPLETED,
            entries=_entries(db_session, paper),
            attempt_id=created.attempt_id,
        )

    db_session.rollback()
    db_session.expire_all()
    owner_attempt = db_session.get(Attempt, created.attempt_id)
    assert owner_attempt.student_id == student.id
    assert owner_attempt.date_completed == DATE_COMPLETED
    assert _completed_count(db_session, intruder) == 0


def test_update_refuses_unknown_attempt(db_session, student, paper):
    """A missing attempt fails the same way as a foreign one — no oracle."""
    with pytest.raises(AttemptNotFoundError):
        save_attempt(
            db_session,
            student_id=student.id,
            paper_id=paper.id,
            date_completed=DATE_COMPLETED,
            entries=_entries(db_session, paper),
            attempt_id=999_999,
        )


def test_update_refuses_changing_the_paper(db_session, student, paper):
    """Re-pointing an attempt at another paper would orphan its result rows."""
    other = _paper(db_session, "9709_12_MJ_2025")
    created = save_attempt(
        db_session,
        student_id=student.id,
        paper_id=paper.id,
        date_completed=DATE_COMPLETED,
        entries=_entries(db_session, paper),
    )

    with pytest.raises(RecordValidationError) as excinfo:
        save_attempt(
            db_session,
            student_id=student.id,
            paper_id=other.id,
            date_completed=DATE_COMPLETED,
            entries=_entries(db_session, other),
            attempt_id=created.attempt_id,
        )
    assert "RP-V-001" in excinfo.value.rule_ids


# --- Validation (§12) -------------------------------------------------------


def test_rp_v_001_paper_and_date_required(db_session, student, paper):
    with pytest.raises(RecordValidationError) as excinfo:
        save_attempt(
            db_session,
            student_id=student.id,
            paper_id=None,
            date_completed=None,
            entries=_entries(db_session, paper),
        )
    assert excinfo.value.rule_ids.count("RP-V-001") == 2


def test_rp_v_001_unknown_paper_rejected(db_session, student, paper):
    with pytest.raises(RecordValidationError) as excinfo:
        save_attempt(
            db_session,
            student_id=student.id,
            paper_id=999_999,
            date_completed=DATE_COMPLETED,
            entries=_entries(db_session, paper),
        )
    assert "RP-V-001" in excinfo.value.rule_ids


def test_rp_v_001_sub_part_from_another_paper_rejected(db_session, student, paper):
    """A row must belong to the paper being recorded."""
    other = _paper(db_session, "9709_12_MJ_2025")
    entries = _entries(db_session, paper)
    entries.append(
        SubPartEntry(
            sub_part_id=_sub_parts(db_session, other)[0].id,
            marks_lost=1,
            error_type="Careless Error",
        )
    )
    with pytest.raises(RecordValidationError) as excinfo:
        save_attempt(
            db_session,
            student_id=student.id,
            paper_id=paper.id,
            date_completed=DATE_COMPLETED,
            entries=entries,
        )
    assert "RP-V-001" in excinfo.value.rule_ids


def test_rp_v_004_blank_marks_lost_rejected(db_session, student, paper):
    with pytest.raises(RecordValidationError) as excinfo:
        save_attempt(
            db_session,
            student_id=student.id,
            paper_id=paper.id,
            date_completed=DATE_COMPLETED,
            entries=_entries(db_session, paper, {3: (None, "Careless Error")}),
        )
    assert "RP-V-004" in excinfo.value.rule_ids


def test_rp_v_004_missing_row_rejected(db_session, student, paper):
    """A sub-part with no row at all is a blank row — the form has all 22."""
    entries = _entries(db_session, paper)
    dropped = entries.pop(7)

    with pytest.raises(RecordValidationError) as excinfo:
        save_attempt(
            db_session,
            student_id=student.id,
            paper_id=paper.id,
            date_completed=DATE_COMPLETED,
            entries=entries,
        )
    violations = [v for v in excinfo.value.violations if v.rule_id == "RP-V-004"]
    assert [v.sub_part_id for v in violations] == [dropped.sub_part_id]


def test_rp_v_005_negative_marks_lost_rejected(db_session, student, paper):
    with pytest.raises(RecordValidationError) as excinfo:
        save_attempt(
            db_session,
            student_id=student.id,
            paper_id=paper.id,
            date_completed=DATE_COMPLETED,
            entries=_entries(db_session, paper, {1: (-1, "Careless Error")}),
        )
    assert "RP-V-005" in excinfo.value.rule_ids


def test_rp_v_006_marks_lost_above_row_max_rejected(db_session, student, paper):
    """The ceiling is THAT row's max_marks, not the paper's."""
    rows = _sub_parts(db_session, paper)
    index = next(i for i, sp in enumerate(rows) if sp.max_marks == 2)

    with pytest.raises(RecordValidationError) as excinfo:
        save_attempt(
            db_session,
            student_id=student.id,
            paper_id=paper.id,
            date_completed=DATE_COMPLETED,
            entries=_entries(db_session, paper, {index: (3, "Conceptual Error")}),
        )
    violations = [v for v in excinfo.value.violations if v.rule_id == "RP-V-006"]
    assert [v.sub_part_id for v in violations] == [rows[index].id]
    assert _completed_count(db_session, student) == 0


def test_rp_v_006_marks_lost_equal_to_max_allowed(db_session, student, paper):
    """Losing every mark on a row is legal — the boundary is inclusive."""
    rows = _sub_parts(db_session, paper)
    index = next(i for i, sp in enumerate(rows) if sp.max_marks == 2)

    result = save_attempt(
        db_session,
        student_id=student.id,
        paper_id=paper.id,
        date_completed=DATE_COMPLETED,
        entries=_entries(db_session, paper, {index: (2, "Conceptual Error")}),
    )
    assert _result_for(db_session, result.attempt_id, rows[index].id).marks_scored == 0


def test_rp_v_007_non_integer_marks_lost_rejected(db_session, student, paper):
    with pytest.raises(RecordValidationError) as excinfo:
        save_attempt(
            db_session,
            student_id=student.id,
            paper_id=paper.id,
            date_completed=DATE_COMPLETED,
            entries=_entries(db_session, paper, {2: (1.5, "Careless Error")}),
        )
    assert "RP-V-007" in excinfo.value.rule_ids


def test_rp_v_007_non_numeric_marks_lost_rejected(db_session, student, paper):
    with pytest.raises(RecordValidationError) as excinfo:
        save_attempt(
            db_session,
            student_id=student.id,
            paper_id=paper.id,
            date_completed=DATE_COMPLETED,
            entries=_entries(db_session, paper, {2: ("two", "Careless Error")}),
        )
    assert "RP-V-007" in excinfo.value.rule_ids


def test_whole_number_from_a_form_post_accepted(db_session, student, paper):
    """A form posts strings; "2" is a whole number, so it is not RP-V-007."""
    rows = _sub_parts(db_session, paper)
    index = next(i for i, sp in enumerate(rows) if sp.max_marks == 5)

    result = save_attempt(
        db_session,
        student_id=student.id,
        paper_id=paper.id,
        date_completed=DATE_COMPLETED,
        entries=_entries(db_session, paper, {index: ("2", "Calculation Error")}),
    )
    assert result.total_marks_lost == 2
    assert _result_for(db_session, result.attempt_id, rows[index].id).marks_scored == 3


def test_rp_v_008_zero_marks_lost_with_error_category_rejected(db_session, student, paper):
    """marks_lost 0 must be "No Error" — the UI lock is not validation."""
    rows = _sub_parts(db_session, paper)

    with pytest.raises(RecordValidationError) as excinfo:
        save_attempt(
            db_session,
            student_id=student.id,
            paper_id=paper.id,
            date_completed=DATE_COMPLETED,
            entries=_entries(db_session, paper, {4: (0, "Conceptual Error")}),
        )
    violations = [v for v in excinfo.value.violations if v.rule_id == "RP-V-008"]
    assert [v.sub_part_id for v in violations] == [rows[4].id]
    assert _completed_count(db_session, student) == 0


def test_rp_v_009_marks_lost_with_no_error_rejected(db_session, student, paper):
    """marks_lost > 0 cannot be "No Error" — a cause is required."""
    rows = _sub_parts(db_session, paper)

    with pytest.raises(RecordValidationError) as excinfo:
        save_attempt(
            db_session,
            student_id=student.id,
            paper_id=paper.id,
            date_completed=DATE_COMPLETED,
            entries=_entries(db_session, paper, {6: (1, NO_ERROR)}),
        )
    violations = [v for v in excinfo.value.violations if v.rule_id == "RP-V-009"]
    assert [v.sub_part_id for v in violations] == [rows[6].id]


def test_rp_v_009_blank_error_type_rejected(db_session, student, paper):
    with pytest.raises(RecordValidationError) as excinfo:
        save_attempt(
            db_session,
            student_id=student.id,
            paper_id=paper.id,
            date_completed=DATE_COMPLETED,
            entries=_entries(db_session, paper, {6: (1, "")}),
        )
    assert "RP-V-009" in excinfo.value.rule_ids


def test_error_type_outside_the_nine_rejected(db_session, student, paper):
    with pytest.raises(RecordValidationError) as excinfo:
        save_attempt(
            db_session,
            student_id=student.id,
            paper_id=paper.id,
            date_completed=DATE_COMPLETED,
            entries=_entries(db_session, paper, {6: (1, "Silly Mistake")}),
        )
    assert "RP-V-009" in excinfo.value.rule_ids


@pytest.mark.parametrize("error_type", FAULT_ERROR_TYPES)
def test_every_fault_error_type_accepted(db_session, student, paper, error_type):
    """All eight non-No-Error values are storable, and stored verbatim."""
    rows = _sub_parts(db_session, paper)
    index = next(i for i, sp in enumerate(rows) if sp.max_marks == 4)

    result = save_attempt(
        db_session,
        student_id=student.id,
        paper_id=paper.id,
        date_completed=DATE_COMPLETED,
        entries=_entries(db_session, paper, {index: (1, error_type)}),
    )
    assert _result_for(db_session, result.attempt_id, rows[index].id).error_type == error_type


def test_rp_v_010_total_marks_lost_above_paper_total_rejected(db_session, student, paper):
    """The total can never exceed the paper's mark scale.

    With consistent reference data RP-V-006 already caps the total at the sum
    of max_marks, so this builds the one case where the total-level guard is
    the only thing standing: a paper whose sub-parts over-sum the 75 marks it
    is stated to be out of. Every row here is individually legal.
    """
    extra_question = Question(paper_id=paper.id, question_number=99)
    db_session.add(extra_question)
    db_session.flush()
    db_session.add(
        SubPart(
            question_id=extra_question.id,
            label="a",
            max_marks=5,
            topic_id=_sub_parts(db_session, paper)[0].topic_id,
            sort_order=99,
        )
    )
    db_session.commit()

    rows = _sub_parts(db_session, paper)
    assert sum(sp.max_marks for sp in rows) == PAPER_TOTAL + 5
    assert paper.total_marks == PAPER_TOTAL

    losses = {i: (sp.max_marks, "Time Pressure") for i, sp in enumerate(rows)}
    with pytest.raises(RecordValidationError) as excinfo:
        save_attempt(
            db_session,
            student_id=student.id,
            paper_id=paper.id,
            date_completed=DATE_COMPLETED,
            entries=_entries(db_session, paper, losses),
        )
    assert "RP-V-010" in excinfo.value.rule_ids
    assert _completed_count(db_session, student) == 0


def test_rp_v_011_duplicate_row_in_one_submission_rejected(db_session, student, paper):
    """The same sub-part twice would collide on UNIQUE(attempt_id, sub_part_id)."""
    entries = _entries(db_session, paper)
    entries.append(
        SubPartEntry(sub_part_id=entries[0].sub_part_id, marks_lost=0, error_type=NO_ERROR)
    )

    with pytest.raises(RecordValidationError) as excinfo:
        save_attempt(
            db_session,
            student_id=student.id,
            paper_id=paper.id,
            date_completed=DATE_COMPLETED,
            entries=entries,
        )
    violations = [v for v in excinfo.value.violations if v.rule_id == "RP-V-011"]
    assert [v.sub_part_id for v in violations] == [entries[0].sub_part_id]


# --- All violations together, never first-fail ------------------------------


def test_all_violations_reported_together(db_session, student, paper):
    """§12: the UI shows every bad row at once, so nothing short-circuits."""
    entries = _entries(
        db_session,
        paper,
        {
            0: (99, "Conceptual Error"),  # RP-V-006 — over any row's max
            1: (-2, "Careless Error"),  # RP-V-005
            2: (1.5, "Careless Error"),  # RP-V-007
            3: (None, "Careless Error"),  # RP-V-004
            4: (0, "Time Pressure"),  # RP-V-008
            6: (1, NO_ERROR),  # RP-V-009
        },
    )
    dropped = entries.pop(9)  # RP-V-004 again, a missing row

    with pytest.raises(RecordValidationError) as excinfo:
        save_attempt(
            db_session,
            student_id=student.id,
            paper_id=paper.id,
            date_completed=None,  # RP-V-001
            entries=entries,
        )

    reported = excinfo.value.rule_ids
    for rule_id in (
        "RP-V-001",
        "RP-V-004",
        "RP-V-005",
        "RP-V-006",
        "RP-V-007",
        "RP-V-008",
        "RP-V-009",
    ):
        assert rule_id in reported, f"{rule_id} was swallowed by an earlier failure"
    assert reported.count("RP-V-004") == 2  # the blank row and the missing one
    assert dropped.sub_part_id in [v.sub_part_id for v in excinfo.value.violations]

    # Rejected whole: a submission with any violation writes nothing.
    assert _completed_count(db_session, student) == 0
    assert db_session.scalar(select(func.count()).select_from(SubPartResult)) == 0


def test_failed_edit_leaves_the_stored_attempt_untouched(db_session, student, paper):
    """A rejected correction must not half-apply to the attempt it was editing."""
    rows = _sub_parts(db_session, paper)
    index = next(i for i, sp in enumerate(rows) if sp.max_marks == 5)

    created = save_attempt(
        db_session,
        student_id=student.id,
        paper_id=paper.id,
        date_completed=DATE_COMPLETED,
        entries=_entries(db_session, paper, {index: (2, "Calculation Error")}),
    )

    with pytest.raises(RecordValidationError):
        save_attempt(
            db_session,
            student_id=student.id,
            paper_id=paper.id,
            date_completed=date(2026, 9, 26),
            entries=_entries(db_session, paper, {index: (99, "Calculation Error")}),
            attempt_id=created.attempt_id,
        )

    db_session.rollback()
    db_session.expire_all()
    assert _result_for(db_session, created.attempt_id, rows[index].id).marks_scored == 3
    assert db_session.get(Attempt, created.attempt_id).date_completed == DATE_COMPLETED
    assert _completed_count(db_session, student) == 1
