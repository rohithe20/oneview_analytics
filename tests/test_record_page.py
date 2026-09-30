"""Record Practice Paper — page shell and the paper-selection cascade.

Covers the BRD's acceptance tests for this slice: RP-T-001 (shared shell,
Record highlighted), RP-T-002/003 (Paper Type filtered by Level), RP-T-004
(sessions for the selected paper), RP-T-005 (variants for that paper/session),
plus §6's "changing Level clears incompatible Paper Type, Session and Variant
selections" and §15's "must be driven by the paper/question database".

The seed CSVs hold only AS Pure papers, so these tests build their own
reference data: both levels and both families, with deliberately different
sessions and variants per paper type. That is what makes "filtered by Level"
and "only valid sessions" falsifiable — against the seed alone, a route that
ignored its filters entirely would still look right.
"""

from __future__ import annotations

import re
from html import unescape

import pytest

from app.models import Paper, Subject
from app.models.enums import ExamSession
from app.services.paper_catalog import paper_type_label, resolve_selection, variant_code

# BRD §6 paper-type filtering rules, quoted from the document.
AS_PAPER_TYPES = ["Paper 1 - Pure Mathematics 1", "Paper 5 - Probability & Statistics 1"]
A_PAPER_TYPES = ["Paper 3 - Pure Mathematics 2", "Paper 5 - Probability & Statistics 2"]

# (level, component, session, year, variant) — the catalogue under test.
# AS/1 and A/3 exist at one level each (the §6 "incompatible" case); component
# 5 exists at both (the "still compatible" case). Sessions and variants differ
# per paper type so a missing filter shows up as a wrong option list.
PAPERS = [
    ("AS", 1, ExamSession.MAY_JUNE, 2025, 1),
    ("AS", 1, ExamSession.MAY_JUNE, 2025, 2),
    ("AS", 1, ExamSession.OCT_NOV, 2025, 3),
    ("AS", 5, ExamSession.MARCH, 2024, 1),
    ("A", 3, ExamSession.MAY_JUNE, 2025, 1),
    ("A", 5, ExamSession.OCT_NOV, 2023, 2),
]


@pytest.fixture
def catalogue(db_session):
    """Papers spanning both levels and both families."""
    subject = Subject(board="Cambridge", code="9709", name="Mathematics")
    db_session.add(subject)
    db_session.flush()

    for level, component, session, year, variant in PAPERS:
        db_session.add(
            Paper(
                subject_id=subject.id,
                component=component,
                variant=variant,
                session=session,
                year=year,
                total_marks=75,
                level=level,
            )
        )
    db_session.commit()
    return subject


def _option_labels(html: str, select_name: str) -> list[str]:
    """The option labels of one <select>, in render order, as the student reads
    them — unescaped, so these compare against the BRD's own wording
    ("Probability & Statistics", not "Probability &amp; Statistics").
    """
    block = re.search(rf'<select[^>]*name="{select_name}"[^>]*>(.*?)</select>', html, re.S)
    assert block, f"no <select name={select_name}> in response"
    options = re.findall(r"<option[^>]*>(.*?)</option>", block.group(1), re.S)
    return [unescape(" ".join(o.split())) for o in options]


def _selected_value(html: str, select_name: str) -> str | None:
    """The `value` of the selected option, or None when nothing is selected."""
    block = re.search(rf'<select[^>]*name="{select_name}"[^>]*>(.*?)</select>', html, re.S)
    assert block, f"no <select name={select_name}> in response"
    match = re.search(r'<option value="([^"]*)"[^>]*\bselected\b', block.group(1))
    return match.group(1) if match else None


# --- §6 paper-type labels ----------------------------------------------------


def test_paper_type_labels_match_the_brd_wording():
    """The four labels §6 names, reproduced exactly."""
    assert paper_type_label("AS", 1, "Pure") == "Paper 1 - Pure Mathematics 1"
    assert paper_type_label("AS", 5, "Statistics") == "Paper 5 - Probability & Statistics 1"
    assert paper_type_label("A", 3, "Pure") == "Paper 3 - Pure Mathematics 2"
    assert paper_type_label("A", 5, "Statistics") == "Paper 5 - Probability & Statistics 2"


def test_variant_code_is_the_component_and_variant_digits():
    """PO decision: a variant displays as the two-digit Cambridge paper code."""
    assert variant_code(1, 1) == "11"
    assert variant_code(1, 2) == "12"
    assert variant_code(3, 3) == "33"
    # No component chosen yet -> the bare variant, never a stray "None2".
    assert variant_code(None, 2) == "2"


def test_paper_type_label_falls_back_for_an_unmapped_component():
    """A paper with no family mapping is named, not guessed at or crashed on."""
    assert paper_type_label("AS", 4, None) == "Paper 4"


# --- RP-T-001: the shared shell ---------------------------------------------


def test_record_page_renders_the_shared_shell(logged_in_client, catalogue):
    response = logged_in_client.get("/record")

    assert response.status_code == 200
    body = response.text

    assert "Record Practice Paper" in body
    assert "Paper Details" in body
    # §5/§17: one nav, the same one Overview uses — not a second sidebar.
    assert body.count("<aside") == 1
    for nav_label in ("Overview", "Topic Analysis"):
        assert nav_label in body


def test_record_nav_item_is_highlighted(logged_in_client, catalogue):
    """RP-T-001: the current page is highlighted with the approved accent."""
    body = logged_in_client.get("/record").text

    record_link = re.search(r'<a href="/record"[^>]*class="([^"]*)"', body, re.S)
    assert record_link, "no /record nav link"
    assert "bg-indigo-600" in record_link.group(1)

    overview_link = re.search(r'<a href="/overview"[^>]*class="([^"]*)"', body, re.S)
    assert overview_link
    assert "bg-indigo-600" not in overview_link.group(1)


def test_record_page_requires_a_session(anonymous_client, catalogue):
    """§19: an anonymous caller is redirected to login, not served the page."""
    response = anonymous_client.get("/record", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_paper_options_fragment_requires_a_session(anonymous_client, catalogue):
    """A fragment of a protected page is protected too."""
    response = anonymous_client.get("/record/paper-options?level=AS", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


# --- §6 / §25.1: field order ------------------------------------------------


def test_paper_details_fields_render_in_the_approved_order(logged_in_client, catalogue):
    """§25.1: Level, Paper Type, Session, Variant, Date Completed."""
    body = logged_in_client.get("/record").text

    positions = [
        body.index(f'name="{name}"')
        for name in ("level", "component", "session", "variant", "date_completed")
    ]
    assert positions == sorted(positions)


# --- RP-T-002 / RP-T-003: Paper Type filtered by Level ----------------------


def test_as_level_shows_only_as_paper_types(logged_in_client, catalogue):
    """RP-T-002."""
    body = logged_in_client.get("/record/paper-options?level=AS").text

    labels = _option_labels(body, "component")
    assert labels == ["Select paper type", *AS_PAPER_TYPES]


def test_a_level_shows_only_a_paper_types(logged_in_client, catalogue):
    """RP-T-003."""
    body = logged_in_client.get("/record/paper-options?level=A").text

    labels = _option_labels(body, "component")
    assert labels == ["Select paper type", *A_PAPER_TYPES]


def test_paper_types_come_from_the_database_not_a_literal_list(db_session, catalogue):
    """§15: the option list is driven by the paper database.

    Deleting every AS Pure paper must remove that paper type — a hard-coded
    §6 list would keep offering it.
    """
    for paper in list(db_session.query(Paper).filter_by(level="AS", component=1)):
        db_session.delete(paper)
    db_session.commit()

    selection = resolve_selection(db_session, "AS")

    assert [option.label for option in selection.paper_types] == [AS_PAPER_TYPES[1]]


def test_level_with_no_papers_offers_nothing(db_session):
    """§18 "No valid paper structure": no options invented for an empty level."""
    selection = resolve_selection(db_session, "A")

    assert selection.paper_types == []
    assert selection.component is None


# --- RP-T-004: sessions for the selected paper ------------------------------


def test_sessions_are_those_of_the_selected_paper(logged_in_client, catalogue):
    """RP-T-004: only valid sessions for the selected paper are available."""
    body = logged_in_client.get("/record/paper-options?level=AS&component=1").text

    labels = _option_labels(body, "session")
    # Newest first; AS/5's March 2024 belongs to the other paper type.
    assert labels == ["Select session", "Oct/Nov 2025", "May/June 2025"]


def test_sessions_are_empty_until_a_paper_type_is_chosen(logged_in_client, catalogue):
    body = logged_in_client.get("/record/paper-options?level=AS").text

    assert _option_labels(body, "session") == ["Select paper type first"]
    assert _option_labels(body, "variant") == ["Select session first"]


# --- RP-T-005: variants for that paper/session ------------------------------


# PO decision (was the open "bare vs combined variant" item): the Variant
# dropdown shows the two-digit Cambridge paper code — component digit then
# variant digit — so component 1 variants 1/2/3 display as 11/12/13. The stored
# OPTION VALUE stays the bare variant, so only these display labels change.
def test_variants_are_shown_as_combined_paper_codes(logged_in_client, catalogue):
    """RP-T-005: available variants, shown as component||variant (11, 12)."""
    body = logged_in_client.get(
        "/record/paper-options?level=AS&component=1&session=MAY_JUNE-2025"
    ).text

    assert _option_labels(body, "variant") == ["Select variant", "11", "12"]
    # The submitted value is still the bare variant, so the cascade resolves it.
    block = re.search(r'<select[^>]*name="variant"[^>]*>(.*?)</select>', body, re.S).group(1)
    assert re.findall(r'<option value="(\d+)"', block) == ["1", "2"]


def test_a_different_session_offers_its_own_variants(logged_in_client, catalogue):
    body = logged_in_client.get(
        "/record/paper-options?level=AS&component=1&session=OCT_NOV-2025"
    ).text

    assert _option_labels(body, "variant") == ["Select variant", "13"]


# --- §6: changing Level clears incompatible selections ----------------------


def test_changing_level_clears_an_incompatible_paper_type(logged_in_client, catalogue):
    """§6 / RP-V-002: AS's Paper 1 does not survive a switch to A Level.

    Session and Variant go with it — with no paper type there is nothing for
    them to be valid against.
    """
    body = logged_in_client.get(
        "/record/paper-options?level=A&component=1&session=MAY_JUNE-2025&variant=1"
    ).text

    assert _selected_value(body, "component") is None
    assert _option_labels(body, "component") == ["Select paper type", *A_PAPER_TYPES]
    assert _option_labels(body, "session") == ["Select paper type first"]
    assert _option_labels(body, "variant") == ["Select session first"]


def test_changing_level_keeps_a_paper_type_that_is_still_offered(logged_in_client, catalogue):
    """§6 clears INCOMPATIBLE selections; component 5 exists at both levels.

    It is relabelled for the new level and its sessions reload — AS/5's
    March 2024 is not an A Level session, so it is dropped.
    """
    body = logged_in_client.get("/record/paper-options?level=A&component=5&session=MARCH-2024").text

    assert _selected_value(body, "component") == "5"
    assert A_PAPER_TYPES[1] in _option_labels(body, "component")
    assert _selected_value(body, "session") is None
    assert _option_labels(body, "session") == ["Select session", "Oct/Nov 2023"]


def test_changing_paper_type_clears_a_stale_session_and_variant(logged_in_client, catalogue):
    """§15: a session that belongs to the previous paper type does not carry over."""
    body = logged_in_client.get(
        "/record/paper-options?level=AS&component=5&session=MAY_JUNE-2025&variant=2"
    ).text

    assert _selected_value(body, "session") is None
    assert _option_labels(body, "session") == ["Select session", "March 2024"]
    assert _option_labels(body, "variant") == ["Select session first"]


def test_unavailable_variant_cannot_be_selected(logged_in_client, catalogue):
    """RP-V-003: a variant not available for the paper/session is cleared."""
    body = logged_in_client.get(
        "/record/paper-options?level=AS&component=1&session=MAY_JUNE-2025&variant=3"
    ).text

    assert _selected_value(body, "variant") is None
    assert _option_labels(body, "variant") == ["Select variant", "11", "12"]


@pytest.mark.parametrize("junk", ["", "nonsense", "1;drop", "99"])
def test_garbage_selections_read_as_nothing_selected(db_session, catalogue, junk):
    """Values arrive from the query string, so anything can turn up."""
    selection = resolve_selection(db_session, "AS", junk, junk, junk)

    assert selection.component is None
    assert selection.paper is None


# --- §15 row 4 / §18: a complete selection resolves to one paper ------------


def test_complete_selection_resolves_to_one_paper(db_session, catalogue):
    selection = resolve_selection(db_session, "AS", "1", "MAY_JUNE-2025", "2")

    assert selection.is_complete
    assert selection.paper.component == 1
    assert selection.paper.variant == 2
    assert selection.paper.level == "AS"
    assert selection.reference == "9709/12 · May/June 2025"


def test_question_table_is_not_populated_until_a_paper_is_selected(logged_in_client, catalogue):
    """§18 "Initial": Paper Details available, question table not populated."""
    body = logged_in_client.get("/record").text

    assert "Choose Paper Type, Session and Variant" in body
    assert "<table" not in body


def test_selected_paper_is_reported_once_the_chain_completes(logged_in_client, catalogue):
    body = logged_in_client.get(
        "/record/paper-options?level=AS&component=1&session=MAY_JUNE-2025&variant=2"
    ).text

    assert "9709/12 · May/June 2025" in body
    # The resolved paper travels to the next task as an id, never a client guess.
    assert re.search(r'name="paper_id" value="\d+"', body)


# --- §5: the page's own Level field is not the shell's level context --------


def test_page_level_field_defaults_to_the_students_own_level(logged_in_client, catalogue):
    """§5: global context is visible; the page also has its own Level field."""
    body = logged_in_client.get("/record").text

    assert _selected_value(body, "level") == "AS"


# --- Question-level table + live Results Summary (§7, §8, §9, §14) -----------
#
# These need a paper WITH question structure, which the `catalogue` fixture
# deliberately omits. This one paper (AS/1, May/June 2025, variant 2) carries a
# topic + sub-topic and sub-parts summing to 75, so the table, the §8 No Error
# lock and the RP-T-011 worked example (lose 7 -> 68/75, 90.7%) are all
# falsifiable against real rows.

from sqlalchemy import select as _sa_select  # noqa: E402

from app.models import Question, SubPart, Topic  # noqa: E402
from app.services.record import ERROR_TYPES  # noqa: E402

# (question_number, label, max_marks) summing to 75.
QUESTION_STRUCTURE = [(1, "", 40), (2, "a", 20), (2, "b", 15)]


@pytest.fixture
def paper_with_questions(db_session):
    subject = Subject(board="Cambridge", code="9709", name="Mathematics")
    db_session.add(subject)
    db_session.flush()

    topic = Topic(subject_id=subject.id, name="Quadratics", parent_id=None)
    db_session.add(topic)
    db_session.flush()
    sub_topic = Topic(subject_id=subject.id, name="Discriminants", parent_id=topic.id)
    db_session.add(sub_topic)
    db_session.flush()

    paper = Paper(
        subject_id=subject.id,
        component=1,
        variant=2,
        session=ExamSession.MAY_JUNE,
        year=2025,
        total_marks=75,
        level="AS",
    )
    db_session.add(paper)
    db_session.flush()

    sub_part_ids = []
    for order, (number, label, marks) in enumerate(QUESTION_STRUCTURE):
        question = db_session.scalar(
            _sa_select(Question).where(
                Question.paper_id == paper.id, Question.question_number == number
            )
        )
        if question is None:
            question = Question(paper_id=paper.id, question_number=number)
            db_session.add(question)
            db_session.flush()
        sub_part = SubPart(
            question_id=question.id,
            label=label,
            max_marks=marks,
            topic_id=sub_topic.id,
            sort_order=order,
        )
        db_session.add(sub_part)
        db_session.flush()
        sub_part_ids.append(sub_part.id)
    db_session.commit()

    paper.sub_part_ids = sub_part_ids  # convenience for the tests
    return paper


COMPLETE_QS = "level=AS&component=1&session=MAY_JUNE-2025&variant=2"


def test_completed_selection_renders_a_flat_question_table(logged_in_client, paper_with_questions):
    """RP-T-006/007: every question and sub-part is a separate flat row with a
    Topic and a Sub-topic."""
    body = logged_in_client.get(f"/record/paper-options?{COMPLETE_QS}").text

    assert "<table" in body
    # One row per sub-part, shown with §7 notation.
    for display in ("1", "2(a)", "2(b)"):
        assert f">{display}</td>" in body
    # Topic vs Sub-topic split from the topic hierarchy.
    assert "Quadratics" in body
    assert "Discriminants" in body
    # Max Marks from the question database, read-only text (not an input).
    for marks in ("40", "20", "15"):
        assert f">{marks}</td>" in body


def test_error_type_dropdown_offers_the_nine_controlled_values(
    logged_in_client, paper_with_questions
):
    """§8: exactly the nine values, no 'Other'."""
    body = logged_in_client.get(f"/record/paper-options?{COMPLETE_QS}").text

    first_id = paper_with_questions.sub_part_ids[0]
    block = re.search(rf'<select[^>]*name="error_type_{first_id}"[^>]*>(.*?)</select>', body, re.S)
    assert block
    raw = re.findall(r"<option[^>]*>(.*?)</option>", block.group(1), re.S)
    options = [unescape(" ".join(o.split())) for o in raw]
    assert options == ["Select error type", *ERROR_TYPES]
    assert "Other" not in options


def test_error_type_is_locked_before_any_marks_are_entered(logged_in_client, paper_with_questions):
    """RP-T-008 / §8: Marks Lost blank (0) -> Error Type locked as No Error."""
    body = logged_in_client.get(f"/record/paper-options?{COMPLETE_QS}").text

    first_id = paper_with_questions.sub_part_ids[0]
    block = re.search(
        rf'<select[^>]*name="error_type_{first_id}"[^>]*>.*?</select>', body, re.S
    ).group(0)
    assert "disabled" in block.split(">", 1)[0]
    assert _selected_value_in(block) == "No Error"


def _selected_value_in(select_html: str) -> str | None:
    match = re.search(r'<option value="([^"]*)"[^>]*\bselected\b', select_html)
    return match.group(1) if match else None


def test_results_summary_starts_at_full_marks(logged_in_client, paper_with_questions):
    """§9: before any Marks Lost, Total Marks 75, nothing lost, 100%."""
    body = logged_in_client.get(f"/record/paper-options?{COMPLETE_QS}").text

    summary = re.search(r'<div id="results-summary".*?</div>\s*</div>', body, re.S).group(0)
    assert "75" in summary
    assert "75 / 75" in summary
    assert "100.0%" in summary


def test_summary_recalculates_from_submitted_marks_lost(logged_in_client, paper_with_questions):
    """RP-T-011/012 / §14: losing 7 marks -> 68/75, 90.7%, derived server-side."""
    first_id = paper_with_questions.sub_part_ids[0]
    response = logged_in_client.post(
        "/record/summary",
        data={"paper_id": str(paper_with_questions.id), f"marks_lost_{first_id}": "7"},
    )

    assert response.status_code == 200
    body = response.text
    assert "68 / 75" in body
    assert "90.7%" in body


def test_summary_ignores_out_of_range_marks_without_erroring(
    logged_in_client, paper_with_questions
):
    """The live preview clamps rather than raising: a value over Max counts as
    Max, so the running total never exceeds the scale mid-entry."""
    first_id = paper_with_questions.sub_part_ids[0]  # Max 40
    response = logged_in_client.post(
        "/record/summary",
        data={"paper_id": str(paper_with_questions.id), f"marks_lost_{first_id}": "999"},
    )

    assert response.status_code == 200
    # Clamped to 40 lost -> 35 / 75.
    assert "35 / 75" in response.text


def test_summary_endpoint_requires_a_session(anonymous_client, paper_with_questions):
    """§19: the recalc fragment is protected like its page."""
    response = anonymous_client.post(
        "/record/summary", data={"paper_id": "1"}, follow_redirects=False
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


# --- Save / Update / Cancel (§10, §11, §12, §16; RP-T-013/015/017) -----------
#
# These drive the whole write path THROUGH the page: the form posts to
# POST /record, which parses it and calls app.services.record.save_attempt (not
# reimplemented here). The service's own contract is covered exhaustively in
# tests/test_record.py; these assert the WIRING — that the form maps to a
# create/update, that a rejected save comes back with every row flagged and
# nothing persisted, and that Cancel touches nothing.

from sqlalchemy import func, select  # noqa: E402

from app.models import Attempt, Student, SubPartResult  # noqa: E402
from app.models.enums import AttemptStatus  # noqa: E402


def _full_form(paper, *, date="2026-09-20", overrides=None, attempt_id=None):
    """A complete, valid POST body for `paper_with_questions`.

    Every sub-part gets a row (the service requires one per sub-part, RP-V-004);
    `overrides` maps a sub_part_id to a (marks_lost, error_type) pair. The
    defaults are "nothing lost, No Error", the shape the real form submits for
    an untouched row after the client normalises blanks to 0.
    """
    overrides = overrides or {}
    form = {"paper_id": str(paper.id), "date_completed": date}
    if attempt_id is not None:
        form["attempt_id"] = str(attempt_id)
    for sub_part_id in paper.sub_part_ids:
        marks_lost, error_type = overrides.get(sub_part_id, ("0", "No Error"))
        form[f"marks_lost_{sub_part_id}"] = str(marks_lost)
        form[f"error_type_{sub_part_id}"] = error_type
    return form


def _completed_count(db, student_id):
    return db.scalar(
        select(func.count())
        .select_from(Attempt)
        .where(Attempt.student_id == student_id, Attempt.status == AttemptStatus.COMPLETED)
    )


def test_save_creates_exactly_one_attempt(
    db_session, logged_in_client, auth_student, paper_with_questions
):
    """RP-T-013 / RP-F-001: a new-form save posts to /record, makes one attempt
    and redirects to Overview so the analytics pick it up."""
    q2a = paper_with_questions.sub_part_ids[1]  # max 20

    response = logged_in_client.post(
        "/record",
        data=_full_form(paper_with_questions, overrides={q2a: ("7", "Careless Error")}),
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/overview"

    db_session.expire_all()
    assert _completed_count(db_session, auth_student.id) == 1


def test_save_stores_the_converted_marks(db_session, logged_in_client, paper_with_questions):
    """RP-T-011 wiring: 7 marks lost on the 20-mark part stores marks_scored 13,
    not the marks lost — the service's conversion reached through the form."""
    q2a = paper_with_questions.sub_part_ids[1]  # max 20

    logged_in_client.post(
        "/record",
        data=_full_form(paper_with_questions, overrides={q2a: ("7", "Careless Error")}),
        follow_redirects=False,
    )

    db_session.expire_all()
    stored = db_session.scalar(select(SubPartResult).where(SubPartResult.sub_part_id == q2a))
    assert stored.marks_scored == 13
    assert stored.error_type == "Careless Error"


def test_save_requires_a_session(anonymous_client, paper_with_questions):
    """§19: the save route is protected — an anonymous POST never records."""
    response = anonymous_client.post(
        "/record", data=_full_form(paper_with_questions), follow_redirects=False
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_update_edits_in_place_without_duplicating(
    db_session, logged_in_client, auth_student, paper_with_questions
):
    """RP-T-015 / RP-F-005/006: editing an existing attempt updates it in place —
    the completed-attempt count does not increase."""
    q2a = paper_with_questions.sub_part_ids[1]  # max 20

    logged_in_client.post(
        "/record",
        data=_full_form(paper_with_questions, overrides={q2a: ("7", "Careless Error")}),
        follow_redirects=False,
    )
    db_session.expire_all()
    attempt_id = db_session.scalar(select(Attempt.id).where(Attempt.student_id == auth_student.id))
    assert _completed_count(db_session, auth_student.id) == 1

    response = logged_in_client.post(
        "/record",
        data=_full_form(
            paper_with_questions,
            date="2026-09-25",
            overrides={q2a: ("2", "Calculation Error")},
            attempt_id=attempt_id,
        ),
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/overview"
    # No duplicate: still one completed attempt, edited in place.
    assert _completed_count(db_session, auth_student.id) == 1

    db_session.expire_all()
    stored = db_session.scalar(select(SubPartResult).where(SubPartResult.sub_part_id == q2a))
    assert stored.marks_scored == 18  # 20 - 2
    assert stored.error_type == "Calculation Error"


def test_page_guards_against_duplicate_submission(logged_in_client, paper_with_questions):
    """RP-V-011: the form drops a second submit so an accidental double-click
    cannot create two attempts (the page's half of idempotency; the service
    de-dupes within a payload)."""
    body = logged_in_client.get("/record").text
    assert "Save Practice Paper" in body
    assert "if (submitted)" in body


def test_edit_page_prepopulates_from_the_saved_attempt(
    db_session, logged_in_client, auth_student, paper_with_questions
):
    """RP-T-014 / §11: opening a saved attempt shows Update, the attempt_id, and
    every stored Marks Lost + Error Type."""
    q2a = paper_with_questions.sub_part_ids[1]  # max 20

    logged_in_client.post(
        "/record",
        data=_full_form(paper_with_questions, overrides={q2a: ("7", "Careless Error")}),
        follow_redirects=False,
    )
    db_session.expire_all()
    attempt_id = db_session.scalar(select(Attempt.id).where(Attempt.student_id == auth_student.id))

    body = logged_in_client.get(f"/record/{attempt_id}/edit").text

    # Primary action is Update, and the attempt rides in a hidden field.
    assert "Update Practice Paper" in body
    assert "Save Practice Paper" not in body
    assert re.search(rf'name="attempt_id"[^>]*value="{attempt_id}"', body)

    # The edited row carries its Marks Lost back, converted from marks_scored.
    marks_input = re.search(rf'<input[^>]*name="marks_lost_{q2a}"[^>]*>', body).group(0)
    assert 'value="7"' in marks_input


def test_edit_of_another_students_attempt_is_not_found(
    db_session, logged_in_client, auth_student, paper_with_questions
):
    """§19: an attempt that isn't yours cannot be opened for editing."""
    intruder = Student(
        username="record_page_intruder",
        display_name="Intruder",
        level="AS",
        password_hash="not-a-real-hash",
    )
    db_session.add(intruder)
    db_session.commit()

    stranger_attempt = Attempt(
        student_id=intruder.id,
        paper_id=paper_with_questions.id,
        status=AttemptStatus.COMPLETED,
    )
    db_session.add(stranger_attempt)
    db_session.commit()

    response = logged_in_client.get(f"/record/{stranger_attempt.id}/edit")
    assert response.status_code == 404


def test_validation_failure_blocks_save_and_flags_every_bad_row(
    db_session, logged_in_client, auth_student, paper_with_questions
):
    """§12/§18: a rejected save persists nothing, flags ALL bad rows at once and
    keeps every entered value."""
    q1 = paper_with_questions.sub_part_ids[0]  # max 40
    q2a = paper_with_questions.sub_part_ids[1]  # max 20

    response = logged_in_client.post(
        "/record",
        data=_full_form(
            paper_with_questions,
            overrides={
                q1: ("50", "Conceptual Error"),  # RP-V-006 — over the row's max
                q2a: ("5", "No Error"),  # RP-V-009 — a loss can't be No Error
            },
        ),
        follow_redirects=False,
    )

    assert response.status_code == 400
    # Nothing was written.
    assert _completed_count(db_session, auth_student.id) == 0

    body = response.text
    # Both bad rows carry the red "needs attention" ring, not just the first.
    for sub_part_id in (q1, q2a):
        cell = re.search(rf'<input[^>]*name="marks_lost_{sub_part_id}"[^>]*>', body).group(0)
        assert "!border-rose-400" in cell, f"row {sub_part_id} not flagged"

    # Entered values are retained (§18): the form is never cleared on rejection.
    assert 'value="50"' in body
    assert 'value="5"' in body


def test_cancel_control_creates_nothing(
    db_session, logged_in_client, auth_student, paper_with_questions
):
    """RP-T-017 / §10: Cancel discards and leaves — it is a plain button, not a
    submit, so reaching or leaving the page records no attempt."""
    # The page carries a Cancel that returns to the previous page client-side.
    page = logged_in_client.get("/record").text
    cancel = re.search(r"<button[^>]*rpCancel\(\)[^>]*>", page).group(0)
    assert 'type="button"' in cancel  # never submits, so it can't hit /record

    # Merely rendering the form (and its Cancel) records nothing.
    assert _completed_count(db_session, auth_student.id) == 0
