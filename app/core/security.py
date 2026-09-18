"""Password hashing for student authentication (login-auth spec).

Uses the maintained `bcrypt` library directly. Plaintext passwords enter
these two functions and go nowhere else — never stored, returned, or logged.
"""

import bcrypt

# bcrypt hashes at most 72 bytes of input. Rather than let a long password be
# silently truncated (which would make two different passwords interchangeable),
# reject it explicitly so the caller sees the limit.
MAX_PASSWORD_BYTES = 72


def _encode(plain: str) -> bytes:
    encoded = plain.encode("utf-8")
    if len(encoded) > MAX_PASSWORD_BYTES:
        raise ValueError(f"Password must be at most {MAX_PASSWORD_BYTES} bytes when UTF-8 encoded.")
    return encoded


def hash_password(plain: str) -> str:
    """Return a bcrypt hash suitable for storing in students.password_hash.

    Raises ValueError if the password exceeds MAX_PASSWORD_BYTES.
    """
    return bcrypt.hashpw(_encode(plain), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Return True if the plaintext matches the stored hash.

    Returns False — never raises — for input bcrypt cannot match: an
    over-long password, or a malformed stored hash such as the seeded
    "not-a-real-hash" placeholder.
    """
    try:
        return bcrypt.checkpw(_encode(plain), hashed.encode("utf-8"))
    except ValueError:
        return False
