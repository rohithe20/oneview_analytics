# Login & Authentication

Source: Overview + Record NFRs ("A student must only access authorized
student data"). Replaces the hardcoded `student_id` with a real session.

## Goal (MVP scope)

A simple, secure login that:
- authenticates a student against a stored password hash,
- establishes a session so `student_id` comes from the session, not a
  hardcoded constant or a query param,
- protects the Overview, Record, and Topic Analysis pages,
- lets a student see ONLY their own data.

This is a single-user-ish demo, but the security requirement is real:
never trust a student_id from the URL.

## Do NOT hand-roll crypto or sessions from scratch

Use a maintained approach. Two acceptable options — pick one, flag it:

1. **Starlette/FastAPI session middleware + passlib** — session cookie
   signed with SECRET_KEY, password hashing via passlib (bcrypt). Minimal
   dependencies, easy to review. RECOMMENDED for this project's size.
2. **fastapi-users** — more batteries, more surface area. Only if the
   extra features are wanted.

Prefer option 1 for MVP: fewer moving parts, easier to reason about.

## Data model

`students` already has `username` and `password_hash`. If password_hash
values are placeholders ("not-a-real-hash"), add a small script/command
to set a real bcrypt hash for the demo student(s).

Add if missing: nothing schema-wise should be needed — username +
password_hash suffice.

## Flow

- `GET /login` → login form (extends the shared shell WITHOUT the
  sidebar, or a minimal centered card).
- `POST /login` → verify username + password against the hash; on
  success set a signed session cookie carrying student_id; redirect to
  `/overview`. On failure, re-render with an error, never revealing
  whether it was the username or password that was wrong.
- `GET /logout` → clear the session, redirect to `/login`.
- A dependency `get_current_student(request)` reads student_id from the
  session; if absent, redirect to `/login`. Every protected route
  depends on it.

## The critical change: student_id from session, not hardcode

Currently Overview/Record use a hardcoded `STUDENT_ID = 1`. Replace with
`get_current_student`. This is the whole security point:

    # before
    student_id = 1
    # after
    student = Depends(get_current_student)
    student_id = student.id

Then the scope filter (student_id, level, family) is driven by WHO IS
LOGGED IN. A logged-in student can never see another student's data
because student_id is never taken from the request — only the session.

## Password hashing

    from passlib.context import CryptContext
    pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
    pwd.hash(password)              # at seed/setup
    pwd.verify(password, stored)    # at login

Never store or log plaintext passwords. SECRET_KEY (already in .env)
signs the session cookie — for deploy it must be a real generated value,
not "change-me".

## Session config

    from starlette.middleware.sessions import SessionMiddleware
    app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY,
                       https_only=<True in prod>, same_site="lax")

## Test contract (tests/test_auth.py)

- Correct credentials → session set, redirect to overview.
- Wrong password → no session, error shown, generic message.
- Unknown username → same generic failure (no user enumeration).
- Protected route without session → redirect to /login.
- get_current_student returns the right student from a valid session.
- A logged-in student's overview uses THEIR student_id, not a param.

## Security checklist (NFR)

- [ ] Passwords hashed (bcrypt), never plaintext.
- [ ] student_id always from session, never from query/body.
- [ ] Session cookie signed; SECRET_KEY real in prod.
- [ ] Login failure message doesn't reveal which field was wrong.
- [ ] Logout clears the session.
- [ ] Protected routes redirect anonymous users to login.

## What NOT to do

- Do NOT take student_id from the URL or form on protected pages.
- Do NOT roll your own password hashing or token signing.
- Do NOT store plaintext or log credentials.
- Do NOT over-build: no registration flow, password reset, email
  verification, or roles for MVP unless asked. One or two seeded
  students with known passwords is enough for the demo.

## Review note (for Rohith)

Auth is the one area to review harder than the engines. When the agent
delivers it, check the security checklist by hand, and confirm no route
reads student_id from the request. An agent can produce auth that "works"
in the happy path but leaks data — the checklist is what catches it.
