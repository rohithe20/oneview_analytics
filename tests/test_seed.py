import pytest
from sqlalchemy import func, select

from app.models import Paper, Question, Subject, SubPart, Topic
from app.seed.demo_attempts import MIN_WEAK_TOPIC_PAPERS, WEAK_TOPIC_NAME
from app.seed.loader import (
    SeedError,
    load_papers,
    load_questions,
    load_subjects,
    load_topics,
)


def run_seed(db):
    subjects = load_subjects(db)
    topics = load_topics(db, subjects)
    papers = load_papers(db, subjects)
    load_questions(db, papers, topics)
    db.commit()


def count(db, model) -> int:
    return db.scalar(select(func.count()).select_from(model))


def test_seed_loads_expected_shape(db_session):
    run_seed(db_session)

    assert count(db_session, Subject) == 1
    assert count(db_session, Topic) == 44  # 8 top-level topics + 36 subtopics
    assert count(db_session, Paper) == 9  # every AS Pure paper in papers.csv
    assert count(db_session, Question) > 0
    assert count(db_session, SubPart) >= count(db_session, Question)


def test_marks_sum_to_paper_total(db_session):
    """The checksum that catches transcription errors — for every paper."""
    run_seed(db_session)

    papers = db_session.scalars(select(Paper)).all()
    assert papers

    for paper in papers:
        total = db_session.scalar(
            select(func.sum(SubPart.max_marks))
            .join(Question, Question.id == SubPart.question_id)
            .where(Question.paper_id == paper.id)
        )
        assert total == paper.total_marks, paper.paper_ref


def test_demo_weak_subtopic_is_carried_by_enough_distinct_papers(db_session):
    """The demo's weak area must clear the priority engine's gate on DISTINCT
    papers alone.

    Only the most recent attempt at a paper counts (planning-performance.md,
    PO decision 2026-09-05), so re-sitting one paper can no longer top up a
    subtopic's observation count. If a questions.csv edit ever leaves
    WEAK_TOPIC_NAME mapped in fewer than MIN_WEAK_TOPIC_PAPERS papers, the
    demo's Priority Areas card silently empties — catch it here rather than
    in the demo.
    """
    run_seed(db_session)

    papers_carrying_it = db_session.scalar(
        select(func.count(func.distinct(Question.paper_id)))
        .select_from(SubPart)
        .join(Question, Question.id == SubPart.question_id)
        .join(Topic, Topic.id == SubPart.topic_id)
        .where(Topic.name == WEAK_TOPIC_NAME)
    )

    assert papers_carrying_it >= MIN_WEAK_TOPIC_PAPERS


def test_seed_is_idempotent(db_session):
    """Running twice must not duplicate anything."""
    run_seed(db_session)
    before = {
        "subjects": count(db_session, Subject),
        "topics": count(db_session, Topic),
        "papers": count(db_session, Paper),
        "questions": count(db_session, Question),
        "sub_parts": count(db_session, SubPart),
    }

    run_seed(db_session)
    after = {
        "subjects": count(db_session, Subject),
        "topics": count(db_session, Topic),
        "papers": count(db_session, Paper),
        "questions": count(db_session, Question),
        "sub_parts": count(db_session, SubPart),
    }

    assert before == after


def test_every_sub_part_has_a_topic(db_session):
    """BR-04 — no orphaned or NULL topic mappings."""
    run_seed(db_session)

    orphans = db_session.scalar(
        select(func.count())
        .select_from(SubPart)
        .outerjoin(Topic, Topic.id == SubPart.topic_id)
        .where(Topic.id.is_(None))
    )
    assert orphans == 0


def test_unknown_topic_name_aborts(db_session, tmp_path, monkeypatch):
    """A typo in topic_name must fail loudly, not insert a NULL."""
    import app.seed.loader as loader

    (tmp_path / "subjects.csv").write_text("board,code,name\nCambridge,9709,Mathematics\n")
    (tmp_path / "topics.csv").write_text(
        "subject_code,name,parent_topic,sort_order\n9709,Trigonometry,,5\n"
    )
    (tmp_path / "papers.csv").write_text(
        "paper_ref,subject_code,component,variant,session,year,total_marks,level\n"
        "TEST_PAPER,9709,1,2,MAY_JUNE,2024,4,AS\n"
    )
    (tmp_path / "questions.csv").write_text(
        "paper_ref,question_number,sub_part_label,max_marks,topic_name\n"
        "TEST_PAPER,1,,4,Trigonometery\n"  # deliberate typo
    )

    monkeypatch.setattr(loader, "DATA_DIR", tmp_path)

    with pytest.raises(SeedError, match="Trigonometery"):
        run_seed(db_session)


def test_mark_total_mismatch_aborts(db_session, tmp_path, monkeypatch):
    """A missing row must be caught by the checksum."""
    import app.seed.loader as loader

    (tmp_path / "subjects.csv").write_text("board,code,name\nCambridge,9709,Mathematics\n")
    (tmp_path / "topics.csv").write_text(
        "subject_code,name,parent_topic,sort_order\n9709,Trigonometry,,5\n"
    )
    (tmp_path / "papers.csv").write_text(
        "paper_ref,subject_code,component,variant,session,year,total_marks,level\n"
        "TEST_PAPER,9709,1,2,MAY_JUNE,2024,75,AS\n"  # claims 75
    )
    (tmp_path / "questions.csv").write_text(
        "paper_ref,question_number,sub_part_label,max_marks,topic_name\n"
        "TEST_PAPER,1,,4,Trigonometry\n"  # only 4 marks present
    )

    monkeypatch.setattr(loader, "DATA_DIR", tmp_path)

    with pytest.raises(SeedError, match="75"):
        run_seed(db_session)


def test_subtopic_resolves_to_parent_id(db_session):
    """A subtopic row's parent_topic must resolve to the real parent's id."""
    run_seed(db_session)

    integration = db_session.scalar(select(Topic).where(Topic.name == "Integration"))
    subtopic = db_session.scalar(
        select(Topic).where(Topic.name == "Definite & indefinite integration")
    )
    assert integration.parent_id is None
    assert subtopic.parent_id == integration.id


def test_unknown_parent_topic_aborts(db_session, tmp_path, monkeypatch):
    """A typo'd or missing parent_topic must fail loudly, not insert a NULL parent."""
    import app.seed.loader as loader

    (tmp_path / "subjects.csv").write_text("board,code,name\nCambridge,9709,Mathematics\n")
    (tmp_path / "topics.csv").write_text(
        "subject_code,name,parent_topic,sort_order\n"
        "9709,Trigonometry,,5\n"
        "9709,Identities,Trigonometery,1\n"  # deliberate typo in parent
    )
    (tmp_path / "papers.csv").write_text(
        "paper_ref,subject_code,component,variant,session,year,total_marks,level\n"
        "TEST_PAPER,9709,1,2,MAY_JUNE,2024,4,AS\n"
    )
    (tmp_path / "questions.csv").write_text(
        "paper_ref,question_number,sub_part_label,max_marks,topic_name\n"
        "TEST_PAPER,1,,4,Trigonometry\n"
    )

    monkeypatch.setattr(loader, "DATA_DIR", tmp_path)

    with pytest.raises(SeedError, match="Trigonometery"):
        run_seed(db_session)


def test_two_level_nesting_aborts(db_session, tmp_path, monkeypatch):
    """A subtopic naming another subtopic as its parent must fail loudly."""
    import app.seed.loader as loader

    (tmp_path / "subjects.csv").write_text("board,code,name\nCambridge,9709,Mathematics\n")
    (tmp_path / "topics.csv").write_text(
        "subject_code,name,parent_topic,sort_order\n"
        "9709,Trigonometry,,5\n"
        "9709,Identities,Trigonometry,1\n"
        "9709,Double-angle identities,Identities,1\n"  # subtopic of a subtopic
    )
    (tmp_path / "papers.csv").write_text(
        "paper_ref,subject_code,component,variant,session,year,total_marks,level\n"
        "TEST_PAPER,9709,1,2,MAY_JUNE,2024,4,AS\n"
    )
    (tmp_path / "questions.csv").write_text(
        "paper_ref,question_number,sub_part_label,max_marks,topic_name\n"
        "TEST_PAPER,1,,4,Trigonometry\n"
    )

    monkeypatch.setattr(loader, "DATA_DIR", tmp_path)

    with pytest.raises(SeedError, match="one level of nesting"):
        run_seed(db_session)


def test_reseed_repoints_subpart_to_new_topic(db_session, tmp_path, monkeypatch):
    """A changed topic_name in questions.csv must reach an already-seeded DB.

    The loader is otherwise insert-only, which silently stranded every
    Integration sub-part on the top-level topic after subtopics were
    added (docs/specs/subtopic-seed.md).
    """
    import app.seed.loader as loader

    (tmp_path / "subjects.csv").write_text("board,code,name\nCambridge,9709,Mathematics\n")
    (tmp_path / "topics.csv").write_text(
        "subject_code,name,parent_topic,sort_order\n"
        "9709,Trigonometry,,5\n"
        "9709,Identities,Trigonometry,1\n"
    )
    (tmp_path / "papers.csv").write_text(
        "paper_ref,subject_code,component,variant,session,year,total_marks,level\n"
        "TEST_PAPER,9709,1,2,MAY_JUNE,2024,4,AS\n"
    )
    questions = tmp_path / "questions.csv"
    header = "paper_ref,question_number,sub_part_label,max_marks,topic_name\n"

    # First load maps the sub-part at the top-level topic.
    questions.write_text(header + "TEST_PAPER,1,,4,Trigonometry\n")
    monkeypatch.setattr(loader, "DATA_DIR", tmp_path)
    run_seed(db_session)

    sub_part = db_session.scalar(select(SubPart))
    top_level = db_session.scalar(select(Topic).where(Topic.name == "Trigonometry"))
    assert sub_part.topic_id == top_level.id

    # The CSV is re-pointed at the subtopic; re-seeding must follow it.
    questions.write_text(header + "TEST_PAPER,1,,4,Identities\n")
    run_seed(db_session)

    subtopic = db_session.scalar(select(Topic).where(Topic.name == "Identities"))
    db_session.refresh(sub_part)
    assert sub_part.topic_id == subtopic.id
    assert count(db_session, SubPart) == 1  # re-pointed, not duplicated
