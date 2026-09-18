"""Password hashing contract (login-auth spec, security checklist)."""

import pytest

from app.core.security import MAX_PASSWORD_BYTES, hash_password, verify_password

PASSWORD = "correct-horse-battery-staple"


def test_verify_accepts_the_original_password():
    assert verify_password(PASSWORD, hash_password(PASSWORD)) is True


def test_verify_rejects_a_wrong_password():
    assert verify_password("not-the-password", hash_password(PASSWORD)) is False


def test_hash_is_not_the_plaintext():
    hashed = hash_password(PASSWORD)
    assert hashed != PASSWORD
    assert PASSWORD not in hashed
    assert hashed.startswith("$2b$")


def test_same_password_hashes_differently_each_time():
    """Per-hash salt: two hashes of one password must not collide."""
    assert hash_password(PASSWORD) != hash_password(PASSWORD)


def test_non_ascii_password_round_trips():
    """UTF-8 encoding is symmetric between hashing and verifying."""
    password = "π-über-sécurité-🔐"
    assert verify_password(password, hash_password(password)) is True


def test_over_long_password_is_rejected_not_truncated():
    """Silent truncation would make two different passwords interchangeable."""
    too_long = "a" * (MAX_PASSWORD_BYTES + 1)
    with pytest.raises(ValueError):
        hash_password(too_long)


def test_verify_returns_false_for_over_long_password():
    """verify_password reports a mismatch rather than raising."""
    assert verify_password("a" * (MAX_PASSWORD_BYTES + 1), hash_password(PASSWORD)) is False


def test_verify_returns_false_for_placeholder_hash():
    """Seeded students still holding "not-a-real-hash" must fail login cleanly."""
    assert verify_password(PASSWORD, "not-a-real-hash") is False
