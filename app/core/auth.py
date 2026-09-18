"""Session-backed authentication (login-auth spec).

The one rule this module exists to enforce: `student_id` comes from the
signed session cookie and from nowhere else — never a query param, path
segment or form field. That is what makes the scope filter
(student_id, exam_level, component_family) trustworthy, and what stops one
student reading another's data by editing a URL.

Password hashing lives next door in `app.core.security`; this module only
decides *who is logged in*.
"""

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models import Student

# The single key written into the session cookie.
SESSION_STUDENT_KEY = "student_id"
LOGIN_URL = "/login"


class NotAuthenticatedError(Exception):
    """No usable session on the request.

    Raised by `get_current_student`. `app.main` registers a handler that turns
    it into a redirect to the login page, so protected routes can simply
    depend on a Student and never handle the anonymous case themselves.
    """


def login_student(request: Request, student: Student) -> None:
    """Record the authenticated student in the session.

    Clears first so a login never inherits state from whatever session the
    caller arrived with.
    """
    request.session.clear()
    request.session[SESSION_STUDENT_KEY] = student.id


def logout_student(request: Request) -> None:
    """Drop the session entirely — the cookie carries nothing afterwards."""
    request.session.clear()


def get_current_student(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> Student:
    """Return the logged-in Student, or raise NotAuthenticatedError.

    A signed cookie proves the id was issued by us, not that the row still
    exists — a deleted or re-seeded student leaves a validly signed session
    pointing at nothing, so that case is treated as logged out and the stale
    cookie is cleared.
    """
    student_id = request.session.get(SESSION_STUDENT_KEY)
    if student_id is None:
        raise NotAuthenticatedError

    student = db.scalar(select(Student).where(Student.id == student_id))
    if student is None:
        request.session.clear()
        raise NotAuthenticatedError

    return student


# Protected routes annotate a parameter with this: `student: CurrentStudent`.
CurrentStudent = Annotated[Student, Depends(get_current_student)]
