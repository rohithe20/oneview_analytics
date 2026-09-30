"""Paper selection catalogue — the Level -> Paper Type -> Session -> Variant
cascade behind the Record Practice Paper page (BRD §6, §15).

This is the thin data-access layer CLAUDE.md asks for: it hands the page its
option lists and resolves a chosen combination to one `papers` row. No
analytics, no engines, no student data — the catalogue is reference data and
is identical for every student.

Two rules from the BRD shape the whole module:

* §15 — "The exact question/sub-part list must be driven by the paper/question
  database. The prototype's sample rows are not production data and must not
  be hard-coded." So every option list here is a query. Nothing in this module
  knows that the seed happens to hold nine AS Pure papers; if a level has no
  papers, the page says so rather than inventing choices.
* §6 — "Changing Level clears incompatible Paper Type, Session and Variant
  selections and reloads the valid choices." `resolve_selection` implements
  that by re-deriving each level of the cascade from the database and dropping
  any inbound selection that is not in the freshly loaded list. That one rule
  also covers RP-V-002 (invalid Level/Paper Type combination cleared) and
  RP-V-003 (a variant not available for the paper/session cannot be selected),
  because an unavailable value simply never survives resolution.

Note "incompatible", not "all": a Paper Type that is still offered after a
Level change survives it. Component 5 exists at both levels, so switching
AS -> A keeps Paper 5 selected and reloads it as "Paper 5 - Probability &
Statistics 2" with that level's sessions. A component that only exists at one
level (1 for AS, 3 for A) is cleared, which is the §6 case.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models import Paper, Question, SubPart, Topic
from app.models.enums import ExamSession

#: The only two exam levels (BRD §6: "Required. Values: AS, A"). AS and A data
#: are never mixed — every query in this module filters on one of them.
LEVELS: tuple[str, ...] = ("AS", "A")

# --- Paper Type labels (BRD §6 filtering rules) ------------------------------
#
# The BRD names exactly four paper types:
#
#     AS -> "Paper 1 - Pure Mathematics 1", "Paper 5 - Probability & Statistics 1"
#     A  -> "Paper 3 - Pure Mathematics 2", "Paper 5 - Probability & Statistics 2"
#
# Those four are not stored as a table of literals, because the SET of paper
# types must come from the papers actually in the database (§15) — a hard-coded
# list would offer a paper type with no papers behind it, and would silently
# hide any paper the seed adds later. Only the LABEL is derived here, from two
# facts that are already reference data: the component's family (the
# `component_families` table) and the syllabus stage the level represents.
#
# `paper_type_label` reproduces all four BRD rows exactly; test_record_page.py
# asserts that against the BRD wording rather than against this code.

#: Family -> the name Cambridge uses in a paper title. Distinct from
#: overview.py's FAMILY_LABELS ("Statistics"), which titles a dashboard panel;
#: here the paper is called "Probability & Statistics" (BRD §6).
FAMILY_PAPER_NAMES: dict[str, str] = {
    "Pure": "Pure Mathematics",
    "Statistics": "Probability & Statistics",
}

#: Level -> the syllabus stage number that ends a paper title. AS papers are
#: the "1" papers (Pure Mathematics 1), A Level the "2" papers.
LEVEL_STAGE: dict[str, int] = {"AS": 1, "A": 2}

#: Chronological order within a year, so sessions can be listed newest-first.
SESSION_ORDER: dict[ExamSession, int] = {
    ExamSession.MARCH: 0,
    ExamSession.MAY_JUNE: 1,
    ExamSession.OCT_NOV: 2,
}


def paper_type_label(level: str, component: int, family: str | None) -> str:
    """The BRD §6 display name for one (level, component) paper type.

    Falls back to a bare "Paper N" for a component with no family mapping or an
    unknown level — an honest label for a paper that exists in the database but
    that the reference data does not describe, rather than a guess or a crash.
    """
    name = FAMILY_PAPER_NAMES.get(family or "")
    stage = LEVEL_STAGE.get(level)
    if name is None or stage is None:
        return f"Paper {component}"
    return f"Paper {component} - {name} {stage}"


@dataclass(frozen=True)
class PaperTypeOption:
    """One Paper Type dropdown option. `component` is the stored value."""

    component: int
    family: str
    label: str


@dataclass(frozen=True)
class SessionOption:
    """One Session dropdown option.

    A Cambridge session is only identifying together with its year, and a paper
    is identified by (subject, component, variant, session, year) — so "Session"
    in BRD §6 is carried here as the session/year pair the prototype shows
    ("May/June 2026"). `key` is the round-trip form value.
    """

    session: ExamSession
    year: int

    @property
    def key(self) -> str:
        return f"{self.session.name}-{self.year}"

    @property
    def label(self) -> str:
        return f"{self.session.value} {self.year}"


def parse_session_key(raw: str | None) -> tuple[ExamSession, int] | None:
    """Read a "MAY_JUNE-2025" form value back, or None if it is not one.

    Never raises: the value arrives from the query string, so anything at all
    can turn up here and an unparseable one is simply "nothing selected".
    """
    if not raw or "-" not in raw:
        return None
    name, _, year = raw.rpartition("-")
    try:
        return ExamSession[name], int(year)
    except (KeyError, ValueError):
        return None


def parse_int(raw: str | int | None) -> int | None:
    """Query-string int, or None. Same tolerance as parse_session_key."""
    try:
        return int(raw) if raw not in (None, "") else None
    except (TypeError, ValueError):
        return None


# --- The four cascade queries (BRD §15) --------------------------------------


def paper_types(db: Session, level: str) -> list[PaperTypeOption]:
    """Paper Types that have at least one paper at this level (§15 row 1).

    `component_families` is reference data created and seeded by migration
    15047ca50390 rather than an ORM model, so it is read as SQL — the same way
    planning.py and the analytics views read it. The join is inner on purpose:
    a component with no family mapping has no place in a page whose whole
    point is the Pure/Statistics split, and it would have no label.
    """
    rows = db.execute(
        text("""
            SELECT DISTINCT p.component AS component, cf.family AS family
            FROM papers p
            JOIN component_families cf ON cf.component = p.component
            WHERE p.level = :level
            ORDER BY p.component
        """),
        {"level": level},
    ).mappings()

    return [
        PaperTypeOption(
            component=row["component"],
            family=row["family"],
            label=paper_type_label(level, row["component"], row["family"]),
        )
        for row in rows
    ]


def sessions_for(db: Session, level: str, component: int) -> list[SessionOption]:
    """Sessions with a paper of this type (§15 row 2), newest first."""
    rows = db.execute(
        select(Paper.session, Paper.year)
        .where(Paper.level == level, Paper.component == component)
        .distinct()
    ).all()

    return sorted(
        (SessionOption(session=session, year=year) for session, year in rows),
        key=lambda option: (option.year, SESSION_ORDER.get(option.session, 0)),
        reverse=True,
    )


def variants_for(
    db: Session, level: str, component: int, session: ExamSession, year: int
) -> list[int]:
    """Variants available for this paper/session (§15 row 3), ascending.

    The BRD's "Example variants: 41, 42, 43" are examples from a Mechanics
    paper, where the quoted number is the component digit followed by the
    variant digit. This schema stores those separately (component on the Paper
    Type, variant here), so what is listed is the stored variant. Flagged in
    docs/open-items.md — the resolved paper is also shown in full Cambridge
    form ("9709/12") so the student can recognise the paper either way.
    """
    return sorted(
        db.scalars(
            select(Paper.variant)
            .where(
                Paper.level == level,
                Paper.component == component,
                Paper.session == session,
                Paper.year == year,
            )
            .distinct()
        ).all()
    )


def find_paper(
    db: Session, level: str, component: int, session: ExamSession, year: int, variant: int
) -> Paper | None:
    """The one paper a complete selection names, or None (§15 row 4).

    `.first()`, not `.one()`: the uniqueness constraint on papers includes
    subject_id, so an unresolvable selection must not raise in a route.
    """
    return db.scalars(
        select(Paper).where(
            Paper.level == level,
            Paper.component == component,
            Paper.session == session,
            Paper.year == year,
            Paper.variant == variant,
        )
    ).first()


def variant_code(component: int | None, variant: int) -> str:
    """The two-digit Cambridge paper code for a variant: the component digit
    followed by the variant digit (component 1, variant 2 -> "12").

    This is how a variant is shown everywhere on the Record page. The paper
    reference already uses it (`paper_reference` renders "9709/12"), and the
    Variant dropdown label now matches, so the two never disagree. Only the
    DISPLAY is combined: the stored value and the cascade's membership checks
    stay the bare `papers.variant`, so resolution is unchanged. PO decision
    logged in docs/open-items.md (was the open "bare vs combined" question).
    """
    return f"{component}{variant}" if component is not None else str(variant)


def paper_reference(paper: Paper) -> str:
    """Cambridge-style identity for a resolved paper, e.g. "9709/12 · May/June 2025"."""
    return (
        f"{paper.subject.code}/{paper.component}{paper.variant} "
        f"· {paper.session.value} {paper.year}"
    )


# --- The cascade itself ------------------------------------------------------


@dataclass
class PaperSelection:
    """Everything the Paper Details fields need: option lists plus what survived.

    A field is None when nothing is selected OR when what was selected is not
    available any more — the page renders both the same way (empty dropdown,
    downstream disabled), which is exactly the §6 "clears incompatible
    selections and reloads the valid choices" behaviour.
    """

    level: str
    paper_types: list[PaperTypeOption] = field(default_factory=list)
    component: int | None = None
    sessions: list[SessionOption] = field(default_factory=list)
    session_key: str | None = None
    variants: list[int] = field(default_factory=list)
    variant: int | None = None
    paper: Paper | None = None

    @property
    def is_complete(self) -> bool:
        """True once all four dropdowns resolve to a real paper.

        The page uses this for BRD §18's Initial state: the question table is
        not populated until sufficient paper context is selected.
        """
        return self.paper is not None

    @property
    def reference(self) -> str | None:
        return paper_reference(self.paper) if self.paper else None


def resolve_selection(
    db: Session,
    level: str,
    component: str | int | None = None,
    session_key: str | None = None,
    variant: str | int | None = None,
) -> PaperSelection:
    """Load every dropdown's options for `level` and keep only valid selections.

    Walks the cascade in BRD §15's order, and at each step drops an inbound
    value that the step above no longer offers. Because each step is skipped
    once its parent is unset, one invalid value upstream clears everything
    below it without any explicit "clear downstream" logic to keep in sync.

    `component`, `session_key` and `variant` come straight from the query
    string, so they are parsed defensively — garbage reads as "not selected",
    never as an error.
    """
    selection = PaperSelection(level=level, paper_types=paper_types(db, level))

    chosen_component = parse_int(component)
    if chosen_component not in {option.component for option in selection.paper_types}:
        return selection
    selection.component = chosen_component

    selection.sessions = sessions_for(db, level, chosen_component)
    parsed_session = parse_session_key(session_key)
    if parsed_session is None or session_key not in {option.key for option in selection.sessions}:
        return selection
    selection.session_key = session_key
    session, year = parsed_session

    selection.variants = variants_for(db, level, chosen_component, session, year)
    chosen_variant = parse_int(variant)
    if chosen_variant not in selection.variants:
        return selection
    selection.variant = chosen_variant

    selection.paper = find_paper(db, level, chosen_component, session, year, chosen_variant)
    return selection


# --- The loaded paper's question/sub-part structure (BRD §7, §15 row 4) ------


@dataclass(frozen=True)
class QuestionRow:
    """One flat row of the Question-level table (BRD §7).

    A question and each of its sub-parts is its OWN row — 2(a) and 2(b) are two
    rows, never a collapsible parent. `sub_part_id` is the stored key the marks
    inputs post back against; the four display columns are read-only, sourced
    from the question database (§17: "Topic and Sub-topic are read-only").
    """

    sub_part_id: int
    display_number: str
    topic: str
    sub_topic: str
    max_marks: int


#: Shown in the Sub-topic column when a sub-part maps straight to a top-level
#: topic (no parent). Every seeded sub-part maps to a leaf, so this is a
#: reference-data guard, not a state the student normally sees.
NO_SUBTOPIC = "\u2014"


def question_display_number(question_number: int, label: str) -> str:
    """The §7 display identifier: "2(a)" for Q2 part a, "1" for an unparted Q1.

    The stored label already carries the sub-part notation (a, b, a(i)), so a
    labelled part is shown as "N(label)" and an unparted question as its bare
    number — never the sequential row index, which is the separate "#" column.
    """
    label = (label or "").strip()
    return f"{question_number}({label})" if label else str(question_number)


def question_rows(db: Session, paper_id: int) -> list[QuestionRow]:
    """The paper's sub-parts as flat table rows, in question then sub-part order.

    Topic vs Sub-topic: a sub-part's `topic_id` points at a LEAF topic (a
    subtopic, via `topics.parent_id`), so the row's Topic is that leaf's parent
    and its Sub-topic is the leaf itself — exactly the split BRD §7 draws
    between the two read-only columns. A sub-part mapped directly to a
    top-level topic (no parent) shows that topic and NO_SUBTOPIC.

    Driven entirely by the question database (§15): nothing here is hard-coded,
    and a paper with no questions yields an empty list, which the page renders
    as §18's "No valid paper structure" rather than an empty table.
    """
    sub_parts = db.scalars(
        select(SubPart)
        .join(SubPart.question)
        .where(Question.paper_id == paper_id)
        .order_by(Question.question_number, SubPart.sort_order, SubPart.id)
    ).all()

    # One pass over the small topics reference table, so the parent lookup is a
    # dict hit rather than a query per row.
    topics = {t.id: t for t in db.scalars(select(Topic)).all()}

    rows: list[QuestionRow] = []
    for sub_part in sub_parts:
        topic = topics.get(sub_part.topic_id)
        parent = topics.get(topic.parent_id) if topic and topic.parent_id else None
        if topic is None:
            topic_name, sub_topic_name = NO_SUBTOPIC, NO_SUBTOPIC
        elif parent is not None:
            topic_name, sub_topic_name = parent.name, topic.name
        else:
            topic_name, sub_topic_name = topic.name, NO_SUBTOPIC

        rows.append(
            QuestionRow(
                sub_part_id=sub_part.id,
                display_number=question_display_number(
                    sub_part.question.question_number, sub_part.label
                ),
                topic=topic_name,
                sub_topic=sub_topic_name,
                max_marks=sub_part.max_marks,
            )
        )
    return rows
