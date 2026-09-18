"""Login / logout pages (login-auth spec).

These are the only routes that read a username or password from the request.
Every other page gets its student from the session via
`app.core.auth.get_current_student`.
"""

from typing import Annotated
from urllib.parse import parse_qsl

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import LOGIN_URL, login_student, logout_student
from app.core.db import get_db
from app.core.security import verify_password
from app.models import Student

router = APIRouter()
templates = Jinja2Templates(directory="app/web/templates")

# ONE message for every failure mode. An unknown username and a wrong password
# must be indistinguishable in status, body and timing-independent content, or
# the form becomes a way to enumerate who has an account.
INVALID_CREDENTIALS = "Invalid username or password"

AFTER_LOGIN_URL = "/overview"


async def _urlencoded_body(request: Request) -> dict[str, str]:
    """Parse an application/x-www-form-urlencoded body.

    Same reason as the copy in overview.py: FastAPI's Form(...) and Starlette's
    request.form() both need python-multipart, which is not a dependency of
    this project (CLAUDE.md: ask before adding one), and HTML forms post
    urlencoded by default — a stdlib parse.
    """
    body = (await request.body()).decode("utf-8", errors="replace")
    return dict(parse_qsl(body, keep_blank_values=True))


def _render_login(
    request: Request,
    username: str = "",
    error: str | None = None,
    status_code: int = 200,
):
    return templates.TemplateResponse(
        request,
        "login.html",
        {"username": username, "error": error},
        status_code=status_code,
    )


@router.get(LOGIN_URL)
def login_form(request: Request):
    return _render_login(request)


@router.post(LOGIN_URL)
async def login_submit(request: Request, db: Annotated[Session, Depends(get_db)]):
    form = await _urlencoded_body(request)
    username = form.get("username", "")
    password = form.get("password", "")

    student = db.scalar(select(Student).where(Student.username == username))

    # One branch for "no such user" and "wrong password" — they must produce
    # the identical response. verify_password never raises, so a student whose
    # hash is still the seeded "not-a-real-hash" placeholder fails here as an
    # ordinary mismatch rather than a 500.
    if student is None or not verify_password(password, student.password_hash):
        # 400, not 401: a 401 must carry a WWW-Authenticate challenge
        # (RFC 9110 §11.6.2) and this is a form, not HTTP authentication. The
        # app already answers rejected form input with a re-rendered 400.
        return _render_login(request, username=username, error=INVALID_CREDENTIALS, status_code=400)

    login_student(request, student)

    # POST/redirect/GET: the session is set, the browser re-requests as a GET.
    return RedirectResponse(url=AFTER_LOGIN_URL, status_code=303)


# POST, not GET: logging out changes state, and a GET endpoint can be fired
# by any third-party page (<img src="/logout">) as a cross-site request.
@router.post("/logout")
def logout(request: Request):
    logout_student(request)
    return RedirectResponse(url=LOGIN_URL, status_code=303)
