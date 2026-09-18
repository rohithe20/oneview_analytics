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

1. **Starlette/FastAPI session middleware + the bcrypt library
   directly** — session cookie signed with SECRET_KEY, password hashing
   via `bcrypt` (no passlib wrapper). Minimal dependencies, easy to
   review. RECOMMENDED for this project's size.
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

Implemented in `app/core/security.py`; tests in `tests/test_security.py`.

    import bcrypt
    bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))

### Why not passlib (decided, do not revisit)

An earlier draft of this spec recommended passlib's `CryptContext`. It
was dropped:

- passlib's last release was 2020. It is unmaintained.
- It does not work with current bcrypt: bcrypt 5.0 turned the >72-byte
  truncation into a hard `ValueError`, which fires inside passlib's own
  backend self-test, so every `hash()` call raises. Making passlib work
  requires pinning `bcrypt<5` — needing a version pin to function at all
  is the signal to avoid the library.
- It logs `(trapped) error reading bcrypt version` once per process on
  any bcrypt >= 4.1, because passlib reads a `__about__` attribute that
  no longer exists. Calling bcrypt directly removes that noise.

Calling bcrypt directly is also simply less code than the wrapper around
it: two one-line functions.

### Two decisions baked into security.py (do not re-litigate)

**1. Passwords over 72 bytes are REJECTED, not truncated.** bcrypt
hashes at most 72 bytes of input. `hash_password` raises `ValueError`
above that rather than letting the tail be dropped, because silent
truncation makes any two passwords sharing a 72-byte prefix
interchangeable at login — a real auth bypass, not a cosmetic limit.
`verify_password` returns `False` for an over-long input so a login
attempt fails as an ordinary mismatch instead of raising. (SHA-256
pre-hashing would lift the limit entirely; rejected for MVP as extra
pipeline for no demo benefit. Nothing stores a real hash yet, so this
can change later without a migration.)

**2. `verify_password` returns False on a malformed stored hash.**
`bcrypt.checkpw` raises `ValueError: Invalid salt` against the seeded
`"not-a-real-hash"` placeholders. Without this, a login attempt by any
student whose hash has not been set with `python -m app.seed.set_password`
would 500 instead of failing cleanly. Anonymous input must never be able
to raise out of the login path.

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
