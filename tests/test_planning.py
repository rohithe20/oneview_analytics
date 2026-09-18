"""Practice-target validation, upsert and the Edit Target route.

Covers docs/specs/planning-performance.md's `set_target` contract
(0 <= value <= available_papers, OV-PL-003), the not-set state (OV-PL-006),
"changing a target never alters historical attempts" (OV-PL-007), the scope
invariant (BRD §32), and docs/specs/overview-completion.md D2's route wiring.

The seed CSVs carry nine Pure AS papers and no Statistics paper, so
available_papers is 9 for AS/Pure and 0 everywhere else — that is what
makes the boundary and zero-available cases real here.
"""

from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import func, select

from app.models import Attempt, Paper, Student, StudyTarget, SubPart, SubPartResult
from app.models.enums import AttemptStatus
from app.seed.loader import load_papers, load_questions, load_subjects, load_topics
from app.services.overview import build_family_overview
from app.services.planning import (
    TargetValidationError,
    get_available_papers,
    get_target,
    set_target,
)

PAPER_REF = "9709_11_MJ_2025"
AS_PURE_PAPERS = 9  # app/seed/data/papers.csv — the OV-PL-003 ceiling for AS/Pure


def _seed_reference_data(db):
    subjects = load_subjects(db)
    topics = load_topics(db, subjects)
    papers = load_papers(db, subjects)
    load_questions(db, papers, topics)
    db.commit()
    return subjects, topics, papers


def _make_student(db) -> Student:
    student = Student(
        username="planning_test_student",
        display_name="Test Student",
        level="AS",
        password_hash="not-a-real-hash",
    )
    db.add(student)
    db.commit()
    return student


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
        db.add(SubPartResult(attempt_id=attempt.id, sub_part_id=sp.id, marks_scored=sp.max_marks))
    db.commit()
    return attempt


# --- Available papers (the validation ceiling) ---


def test_available_papers_counts_only_the_scope(db_session):
    _seed_reference_data(db_session)

    assert get_available_papers(db_session, "AS", "Pure") == AS_PURE_PAPERS
    assert get_available_papers(db_session, "AS", "Statistics") == 0
    assert get_available_papers(db_session, "A", "Pure") == 0


# --- set_target: validation (OV-PL-003) ---


def test_set_target_rejects_negative(db_session):
    _seed_reference_data(db_session)
    student = _make_student(db_session)

    with pytest.raises(TargetValidationError):
        set_target(db_session, student.id, "AS", "Pure", -1)

    assert get_target(db_session, student.id, "AS", "Pure") is None


def test_set_target_rejects_value_above_available_papers(db_session):
    _seed_reference_data(db_session)
    student = _make_student(db_session)

    # Nine Pure AS papers are seeded, so 10 is over the ceiling.
    with pytest.raises(TargetValidationError):
        set_target(db_session, student.id, "AS", "Pure", AS_PURE_PAPERS + 1)

    assert get_target(db_session, student.id, "AS", "Pure") is None


def test_set_target_accepts_the_boundaries(db_session):
    _seed_reference_data(db_session)
    student = _make_student(db_session)

    zero = set_target(db_session, student.id, "AS", "Pure", 0)
    assert zero.target_value == 0

    ceiling = set_target(db_session, student.id, "AS", "Pure", AS_PURE_PAPERS)
    assert ceiling.target_value == AS_PURE_PAPERS


def test_set_target_rejects_any_positive_value_when_no_papers_available(db_session):
    _seed_reference_data(db_session)
    student = _make_student(db_session)

    with pytest.raises(TargetValidationError):
        set_target(db_session, student.id, "AS", "Statistics", 1)

    # 0 is still valid — it is the not-set state, not a violation.
    assert set_target(db_session, student.id, "AS", "Statistics", 0).target_value == 0


# --- set_target: upsert, not insert-twice ---


def test_set_target_upserts_rather_than_duplicating(db_session):
    _seed_reference_data(db_session)
    student = _make_student(db_session)

    first = set_target(db_session, student.id, "AS", "Pure", 1)
    second = set_target(db_session, student.id, "AS", "Pure", 0)

    assert first.id == second.id
    assert second.target_value == 0

    row_count = db_session.scalar(
        select(func.count())
        .select_from(StudyTarget)
        .where(
            StudyTarget.student_id == student.id,
            StudyTarget.exam_level == "AS",
            StudyTarget.component_family == "Pure",
        )
    )
    assert row_count == 1


# --- Scope independence (BRD §32, §6, §35) ---


def test_targets_are_independent_across_families_and_levels(db_session):
    _seed_reference_data(db_session)
    student = _make_student(db_session)

    set_target(db_session, student.id, "AS", "Pure", 1)

    assert get_target(db_session, student.id, "AS", "Pure").target_value == 1
    assert get_target(db_session, student.id, "AS", "Statistics") is None
    assert get_target(db_session, student.id, "A", "Pure") is None


# --- OV-PL-007: a target change never touches historical attempts ---


def test_changing_target_does_not_alter_attempts_or_analytics(db_session):
    _, _, papers = _seed_reference_data(db_session)
    student = _make_student(db_session)
    _record_attempt(db_session, student, papers[PAPER_REF], datetime(2026, 1, 1))

    before = build_family_overview(db_session, student.id, "AS", "Pure")
    assert before.metrics.target_value is None
    assert before.metrics.completion_percentage is None  # OV-PL-006, no divide-by-zero

    set_target(db_session, student.id, "AS", "Pure", 1)
    after = build_family_overview(db_session, student.id, "AS", "Pure")

    assert after.attempts_count == before.attempts_count
    assert after.metrics.average_percentage == before.metrics.average_percentage
    assert after.metrics.recent_percentage == before.metrics.recent_percentage
    assert after.trend_points == before.trend_points
    assert after.predicted_percentage == before.predicted_percentage

    # Only the target and the metric derived from it moved.
    assert after.metrics.target_value == 1
    assert after.metrics.completion_percentage == 100.0


def test_target_of_zero_yields_the_not_set_state_not_a_divide_by_zero(db_session):
    _, _, papers = _seed_reference_data(db_session)
    student = _make_student(db_session)
    _record_attempt(db_session, student, papers[PAPER_REF], datetime(2026, 1, 1))

    set_target(db_session, student.id, "AS", "Pure", 0)
    overview = build_family_overview(db_session, student.id, "AS", "Pure")

    assert overview.metrics.target_value == 0
    assert overview.metrics.completion_percentage is None


# --- The Edit Target route (overview-completion.md D2) ---


@pytest.fixture
def client(db_session, logged_in_client):
    """TestClient with the reference data seeded and `auth_student` logged in.

    The route takes student_id from the session (login-auth spec), so these
    tests assert against `auth_student.id` — whatever the database assigned —
    rather than a hardcoded constant.
    """
    _seed_reference_data(db_session)
    return logged_in_client


def test_overview_requires_a_logged_in_student(anonymous_client):
    """No session, no data: the scope filter has no student to be built from."""
    response = anonymous_client.get("/overview", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_post_target_requires_a_logged_in_student(anonymous_client, db_session):
    _seed_reference_data(db_session)

    response = anonymous_client.post(
        "/overview/target",
        data={"level": "AS", "family": "Pure", "target_value": "1"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/login"
    # Rejected before the service ran — no target was written for anyone.
    assert db_session.scalar(select(func.count()).select_from(StudyTarget)) == 0


def test_the_route_ignores_a_student_id_in_the_request(client, db_session, auth_student):
    """A posted student_id must not move the target off the session's student.

    This is the security property in BRD/NFR terms: student_id is never read
    from the request, so smuggling one in changes nothing.
    """
    other = Student(
        username="someone_else",
        display_name="Other Student",
        level="AS",
        password_hash="not-a-real-hash",
    )
    db_session.add(other)
    db_session.commit()

    response = client.post(
        "/overview/target",
        data={
            "level": "AS",
            "family": "Pure",
            "target_value": "1",
            "student_id": str(other.id),
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert get_target(db_session, auth_student.id, "AS", "Pure").target_value == 1
    assert get_target(db_session, other.id, "AS", "Pure") is None


def test_post_target_persists_and_redirects(client, db_session, auth_student):
    response = client.post(
        "/overview/target",
        data={"level": "AS", "family": "Pure", "target_value": "1"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/overview?level=AS"
    assert get_target(db_session, auth_student.id, "AS", "Pure").target_value == 1


def test_post_target_updates_an_existing_target(client, db_session, auth_student):
    set_target(db_session, auth_student.id, "AS", "Pure", 1)

    response = client.post(
        "/overview/target",
        data={"level": "AS", "family": "Pure", "target_value": "0"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert get_target(db_session, auth_student.id, "AS", "Pure").target_value == 0


def test_post_target_above_available_papers_is_rejected(client, db_session, auth_student):
    response = client.post(
        "/overview/target",
        data={"level": "AS", "family": "Pure", "target_value": "50"},
        follow_redirects=False,
    )

    assert response.status_code == 400
    assert f"Target must be between 0 and {AS_PURE_PAPERS}" in response.text
    assert get_target(db_session, auth_student.id, "AS", "Pure") is None


def test_post_target_negative_is_rejected(client, db_session, auth_student):
    response = client.post(
        "/overview/target",
        data={"level": "AS", "family": "Pure", "target_value": "-3"},
        follow_redirects=False,
    )

    assert response.status_code == 400
    assert get_target(db_session, auth_student.id, "AS", "Pure") is None


def test_post_target_non_numeric_is_rejected(client, db_session, auth_student):
    response = client.post(
        "/overview/target",
        data={"level": "AS", "family": "Pure", "target_value": "many"},
        follow_redirects=False,
    )

    assert response.status_code == 400
    assert get_target(db_session, auth_student.id, "AS", "Pure") is None


def test_post_target_rejects_an_unknown_scope(client, db_session):
    response = client.post(
        "/overview/target",
        data={"level": "AS", "family": "Mechanics", "target_value": "1"},
        follow_redirects=False,
    )

    assert response.status_code == 404

    response = client.post(
        "/overview/target",
        data={"level": "O", "family": "Pure", "target_value": "1"},
        follow_redirects=False,
    )

    assert response.status_code == 404


def test_overview_page_renders_the_stored_target(client, db_session, auth_student):
    set_target(db_session, auth_student.id, "AS", "Pure", 1)

    response = client.get("/overview?level=AS")

    assert response.status_code == 200
    assert "1 papers" in response.text  # "Practice Target: 1 papers"
    assert "Edit Target" in response.text


def test_overview_page_shows_not_set_without_a_target(client):
    response = client.get("/overview?level=AS")

    assert response.status_code == 200
    assert "Not set" in response.text
