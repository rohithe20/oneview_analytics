import os
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from alembic import command
from app.core.db import Base

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
