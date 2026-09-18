import os
from pathlib import Path

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from alembic import command
from app.core.db import Base, get_db
from app.core.security import hash_password
from app.main import app
from app.models import Student

TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://oneview:oneview@localhost:5433/oneview_test",
)

# Extra tables/views alembic creates via raw SQL that aren't SQLAlchemy models,
# so Base.metadata doesn't know to truncate them between tests.
EXTRA_TRUNCATE_TABLES = ["study_targets"]


@pytest.fixture(scope="session")
def engine():
    admin_url = TEST_DATABASE_URL.rsplit("/", 1)[0] + "/postgres"
    admin = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text("DROP DATABASE IF EXISTS oneview_test"))
        conn.execute(text("CREATE DATABASE oneview_test"))
    admin.dispose()

    # Run the real migrations rather than Base.metadata.create_all so the
    # test DB also gets the analytics views and non-ORM tables (study_targets,
    # component_families) that build_family_overview depends on.
    alembic_cfg = Config(str(Path(__file__).resolve().parent.parent / "alembic.ini"))
    alembic_cfg.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
    command.upgrade(alembic_cfg, "head")

    eng = create_engine(TEST_DATABASE_URL)
    yield eng
    eng.dispose()


@pytest.fixture
def db_session(engine):
    """A clean session per test — truncates everything afterwards."""
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    session = SessionLocal()
    yield session
    session.rollback()

    table_names = [t.name for t in reversed(Base.metadata.sorted_tables)] + EXTRA_TRUNCATE_TABLES
    tables = ", ".join(table_names)
    session.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    session.commit()
    session.close()


# --- Authenticated sessions (login-auth spec) -------------------------------
#
# Protected routes take student_id from the signed session cookie and from
# nowhere else, so a route test needs a real login rather than a hardcoded id.

LOGIN_USERNAME = "session_test_student"
LOGIN_PASSWORD = "correct-horse-battery-staple"

# Hashed once at import: bcrypt is deliberately slow, and the cost is the same
# for every test that needs a student who can log in.
LOGIN_PASSWORD_HASH = hash_password(LOGIN_PASSWORD)


@pytest.fixture
def auth_student(db_session) -> Student:
    """A student with a real bcrypt hash, able to log in with LOGIN_PASSWORD.

    Tests assert against `auth_student.id` rather than a constant — the id is
    whatever the database assigns, which is the point: nothing in the app
    depends on a particular student being id 1 any more.
    """
    student = Student(
        username=LOGIN_USERNAME,
        display_name="Test Student",
        level="AS",
        password_hash=LOGIN_PASSWORD_HASH,
    )
    db_session.add(student)
    db_session.commit()
    return student


@pytest.fixture
def anonymous_client(db_session):
    """A TestClient wired to the test session, carrying no session cookie."""
    app.dependency_overrides[get_db] = lambda: db_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def logged_in_client(anonymous_client, auth_student):
    """A TestClient holding a genuine signed session cookie for `auth_student`.

    It logs in through POST /login rather than writing the session dict
    directly, so route tests travel the same path a browser does: if the
    cookie ever stops authenticating, these fail alongside the auth tests
    instead of passing on a hand-made session.
    """
    response = anonymous_client.post(
        "/login",
        data={"username": LOGIN_USERNAME, "password": LOGIN_PASSWORD},
        follow_redirects=False,
    )
    assert response.status_code == 303, "fixture login failed"
    return anonymous_client
