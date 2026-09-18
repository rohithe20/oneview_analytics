"""Set a real bcrypt password hash for a student.

    python -m app.seed.set_password <username> <password>

Replaces the placeholder "not-a-real-hash" values seeded for the demo.
If the password is omitted it is read from a no-echo prompt, which keeps
it out of shell history.
"""

import sys
from getpass import getpass

from sqlalchemy import select

from app.core.db import SessionLocal
from app.core.security import hash_password
from app.models import Student

USAGE = "usage: python -m app.seed.set_password <username> [password]"


def main(argv: list[str]) -> int:
    if not 1 <= len(argv) <= 2:
        print(USAGE, file=sys.stderr)
        return 2

    username = argv[0]
    password = argv[1] if len(argv) == 2 else getpass(f"New password for {username}: ")
    if not password:
        print("Password must not be empty.", file=sys.stderr)
        return 2

    try:
        hashed = hash_password(password)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 2

    with SessionLocal() as db:
        student = db.scalar(select(Student).where(Student.username == username))
        if student is None:
            print(f"No student with username {username!r}.", file=sys.stderr)
            return 1

        student.password_hash = hashed
        db.commit()

    print(f"Password updated for {username}.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
