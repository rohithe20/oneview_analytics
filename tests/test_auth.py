"""Login, logout and the session dependency (login-auth spec).

These tests are the security checklist in executable form. The properties that
matter here are not "login works" but: a failure never says *which* field was
wrong, a failure leaves no session behind, an anonymous caller cannot reach a
protected route, and student_id is only ever read from a signed cookie.
"""

from __future__ import annotations

from typing import Annotated

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.auth import get_current_student
from app.core.config import PLACEHOLDER_SECRET_KEY, Settings
from app.core.db import get_db
from app.core.security import hash_password
from app.main import app
from app.models import Student
from app.web.routes.auth import INVALID_CREDENTIALS

USERNAME = "demo_student"
PASSWORD = "correct-horse-battery-staple"

# A second student whose password was never set with
# `python -m app.seed.set_password` — still carrying the seeded placeholder.
UNSET_USERNAME = "never_set_a_password"

SESSION_COOKIE = "session"


# A stand-in for the pages the spec protects. Overview now depends on
# get_current_student for real (see tests/test_planning.py); this route keeps
# the dependency, the middleware and the redirect handler under test on their
# own, with no page's data requirements in the way.
@app.get("/_test/whoami")
def _whoami(student: Annotated[Student, Depends(get_current_student)]):
    return {"student_id": student.id, "username": student.username}


def _make_student(db, username: str, password_hash: str) -> Student:
    student = Student(
        username=username,
        display_name="Test Student",
        level="AS",
        password_hash=password_hash,
    )
    db.add(student)
    db.commit()
    return student


@pytest.fixture
def student(db_session) -> Student:
    return _make_student(db_session, USERNAME, hash_password(PASSWORD))


@pytest.fixture
def client(db_session, student):
    _make_student(db_session, UNSET_USERNAME, "not-a-real-hash")

    app.dependency_overrides[get_db] = lambda: db_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _login(client, username: str, password: str):
    return client.post(
        "/login",
        data={"username": username, "password": password},
        follow_redirects=False,
    )


def _has_session(client) -> bool:
    return client.cookies.get(SESSION_COOKIE) not in (None, "")


# --- The login page ---


def test_login_page_renders_a_form_without_the_nav(client):
    response = client.get("/login")

    assert response.status_code == 200
    assert 'name="username"' in response.text
    assert 'type="password"' in response.text
    # The sidebar belongs to authenticated pages only.
    assert "Topic Analysis" not in response.text


# --- Success ---


def test_correct_credentials_set_the_session_and_redirect_to_overview(client, student):
    response = _login(client, USERNAME, PASSWORD)

    assert response.status_code == 303
    assert response.headers["location"] == "/overview"
    assert _has_session(client)

    # The session actually identifies this student, not just "someone".
    whoami = client.get("/_test/whoami")
    assert whoami.status_code == 200
    assert whoami.json() == {"student_id": student.id, "username": USERNAME}


# --- Failure: generic, identical, session-free ---


def test_wrong_password_shows_the_generic_error_and_sets_no_session(client):
    response = _login(client, USERNAME, "not-the-password")

    assert response.status_code == 400
    assert INVALID_CREDENTIALS in response.text
    assert not _has_session(client)
    # And the caller is still anonymous as far as protected routes care.
    assert client.get("/_test/whoami", follow_redirects=False).status_code == 303


def test_unknown_username_gives_the_same_generic_failure(client):
    unknown = _login(client, "no-such-student", PASSWORD)
    wrong_password = _login(client, USERNAME, "not-the-password")

    assert unknown.status_code == wrong_password.status_code == 400
    assert INVALID_CREDENTIALS in unknown.text
    assert not _has_session(client)


def test_failure_responses_do_not_reveal_which_field_was_wrong(client):
    """No user enumeration: the two failures must be indistinguishable.

    A distinct message, a different status, or any extra markup on one of them
    would let an anonymous caller test whether an account exists. The only
    difference allowed is the username echoed back into the form — that is the
    caller's own input, which tells them nothing they did not already send —
    so it is normalised out before the bodies are compared.
    """
    unknown_name = "no-such-student"
    unknown = _login(client, unknown_name, "whatever")
    existing = _login(client, USERNAME, "whatever")

    assert unknown.status_code == existing.status_code
    assert unknown.text.replace(unknown_name, "_") == existing.text.replace(USERNAME, "_")


def test_a_student_whose_hash_is_still_the_placeholder_fails_cleanly(client):
    """The seeded "not-a-real-hash" makes bcrypt raise; login must not 500."""
    response = _login(client, UNSET_USERNAME, PASSWORD)

    assert response.status_code == 400
    assert INVALID_CREDENTIALS in response.text
    assert not _has_session(client)


def test_empty_credentials_fail_generically(client):
    response = _login(client, "", "")

    assert response.status_code == 400
    assert INVALID_CREDENTIALS in response.text
    assert not _has_session(client)


# --- Logout ---


def test_logout_clears_the_session(client):
    _login(client, USERNAME, PASSWORD)
    assert _has_session(client)

    response = client.post("/logout", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"
    assert not _has_session(client)
    # The protected route is out of reach again.
    assert client.get("/_test/whoami", follow_redirects=False).status_code == 303


def test_logout_is_not_reachable_by_get(client):
    """A GET /logout would let any third-party page log the student out."""
    _login(client, USERNAME, PASSWORD)

    response = client.get("/logout", follow_redirects=False)

    assert response.status_code == 405
    assert _has_session(client)


# --- get_current_student / protected routes ---


def test_protected_route_redirects_an_anonymous_caller_to_login(client):
    response = client.get("/_test/whoami", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_a_forged_session_cookie_is_rejected(client):
    """The cookie is signed: a hand-written student_id must not authenticate."""
    client.cookies.set(SESSION_COOKIE, "eyJzdHVkZW50X2lkIjogMX0=")

    response = client.get("/_test/whoami", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_a_session_pointing_at_a_deleted_student_is_treated_as_logged_out(
    client, db_session, student
):
    _login(client, USERNAME, PASSWORD)

    db_session.delete(student)
    db_session.commit()

    response = client.get("/_test/whoami", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


# --- SECRET_KEY startup guard ---


def test_a_deployed_environment_refuses_the_placeholder_secret():
    """A cookie signed with the public placeholder key is forgeable."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            DATABASE_URL="postgresql+psycopg://x@localhost/x",
            SECRET_KEY=PLACEHOLDER_SECRET_KEY,
            ENVIRONMENT="production",
        )

    assert PLACEHOLDER_SECRET_KEY in str(exc_info.value)


def test_a_deployed_environment_boots_with_a_real_secret():
    settings = Settings(
        DATABASE_URL="postgresql+psycopg://x@localhost/x",
        SECRET_KEY="a-real-generated-value",
        ENVIRONMENT="production",
    )

    assert settings.is_local is False


@pytest.mark.parametrize("environment", ["local", "development", "  LOCAL  "])
def test_local_environments_may_keep_the_placeholder(environment):
    """Nobody has to invent a secret to run the app on their laptop."""
    settings = Settings(
        DATABASE_URL="postgresql+psycopg://x@localhost/x",
        SECRET_KEY=PLACEHOLDER_SECRET_KEY,
        ENVIRONMENT=environment,
    )

    assert settings.is_local is True


# --- The shared shell's Log out control ---


def test_the_shell_posts_to_logout_and_logging_out_from_it_works(logged_in_client):
    """The sidebar's "Log out" button must reach POST /logout, not GET.

    Rendering the control and exercising the route it names in one test is
    what stops the button drifting away from the endpoint.
    """
    page = logged_in_client.get("/overview")

    assert page.status_code == 200
    assert 'action="/logout"' in page.text
    assert 'method="post"' in page.text
    assert "Log out" in page.text

    logged_in_client.post("/logout", follow_redirects=False)

    assert logged_in_client.get("/overview", follow_redirects=False).status_code == 303
