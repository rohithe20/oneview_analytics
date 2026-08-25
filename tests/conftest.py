import os

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core.db import Base

TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://oneview:oneview@localhost:5433/oneview_test",
)


@pytest.fixture(scope="session")
def engine():
    admin_url = TEST_DATABASE_URL.rsplit("/", 1)[0] + "/postgres"
    admin = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text("DROP DATABASE IF EXISTS oneview_test"))
        conn.execute(text("CREATE DATABASE oneview_test"))
    admin.dispose()

    eng = create_engine(TEST_DATABASE_URL)
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def db_session(engine):
    """A clean session per test — truncates everything afterwards."""
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    session = SessionLocal()
    yield session
    session.rollback()

    tables = ", ".join(t.name for t in reversed(Base.metadata.sorted_tables))
    session.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    session.commit()
    session.close()