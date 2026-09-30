"""Record Practice Paper — the write path (docs/specs/record-service.md).

Takes MARKS LOST per sub-part plus an error type, validates the whole
submission at once, and persists it as ONE attempt (create) or updates an
existing attempt in place (edit). No analytics, no engines — data capture only
(§16, §18).

THE CONVERSION: the student enters marks LOST; the schema stores
marks_scored. `marks_scored = max_marks - marks_lost`, done in one place
(`_write_results`). Every analytic reads marks_scored, so storing
marks_lost there would invert every downstream number.

Interpretations taken where §12's rule list is thinner than the schema
(flagged in docs/open-items.md):

* RP-V-004 ("Marks Lost blank on any row") is read as requiring an entry for
  EVERY sub-part of the paper. A missing entry is a blank row. This also keeps
  the write path consistent with `v_attempt_totals`, which derives the
  denominator by summing max_marks over the sub-parts that HAVE result rows: a
  partial submission would make the analytics disagree with the total this
  service returns, breaking BRD §32 rule 8.
* `total_marks` is summed from the paper's sub-parts, not the literal 75 —
  BRD §32 rule 3 forbids hard-coded prototype values. It is 75 for every
  seeded MVP paper.
* RP-V-010's ceiling is the paper's STATED scale (`papers.total_marks`), not
  the summed one. With consistent reference data RP-V-006 already caps the
  total at the sum, so making RP-V-010 compare against the sum would leave it
  dead code; comparing against the stated total keeps it a real guard — it
  fires when a paper's sub-parts over-sum the scale they are marked out of.
* Ownership failure on edit raises `AttemptNotFoundError`, the same error as a
  missing attempt, so the caller cannot distinguish "not yours" from "does not
  exist" (§19). It is an authorization failure, not a form violation, so it is
  raised on its own rather than collected with the RP-V-* list.
* RP-V-011 idempotency: this service rejects a payload naming the same
  sub-part twice (the UNIQUE(attempt_id, sub_part_id) case the spec cites).
  Attempt-level double-submit protection is the page's submit-disable, per the
  spec's "a submit-token or button-disable is acceptable for MVP" — no token
  column is introduced here.

RP-F-007: nothing is cached. Analytics are computed on read (views + engines),
so a saved or updated attempt is live in Overview / Topic Analysis on their
next query. There is no recalculate step for the caller to trigger.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Attempt, Paper, SubPart, SubPartResult
from app.models.enums import AttemptStatus

# --- The nine controlled error types (§8) -----------------------------------
#
# Data driven, in one place (Maintainability NFR) — no string literals
# scattered through the service, the routes or the templates.

NO_ERROR = "No Error"

ERROR_TYPES: tuple[str, ...] = (
    NO_ERROR,
    "Conceptual Error",
    "Calculation Error",
    "Careless Error",
    "Application Error",
    "Misread Question",
    "Incomplete Answer",
    "Time Pressure",
    "Forgot Formula / Rule",
)

#: The eight that mean marks were lost — everything except "No Error".
FAULT_ERROR_TYPES: tuple[str, ...] = tuple(e for e in ERROR_TYPES if e != NO_ERROR)

#: Percentages are rounded to 2dp to match `v_attempt_totals`' ROUND(..., 2),
#: so the number this service returns is the number the analytics report for
#: the same attempt (BRD §32 rule 8).
PERCENTAGE_DIGITS = 2


@dataclass
class SubPartEntry:
    """One row of the form: marks lost on a sub-part, and why."""

    sub_part_id: int
    marks_lost: int
    error_type: str


@dataclass
class RecordResult:
    """What was saved. Every figure here is derived, never accepted (§14).

    RP-F-007: analytics read through views, so these are already reflected in
    Overview / Topic Analysis — the caller triggers no recalculation.
    """

    attempt_id: int
    total_marks: int
    total_marks_lost: int
    total_score: int
    percentage: float


@dataclass(frozen=True)
class Violation:
    """One broken rule, carrying the §12 ID so the UI can point at the row."""

    rule_id: str
    message: str
    sub_part_id: int | None = None


class RecordValidationError(ValueError):
    """Every violation in one submission, collected — never first-fail.

    The UI shows all bad rows at once, so this carries the whole list the way
    the seed loader does (app/seed/loader.py).
    """

    def __init__(self, violations: list[Violation]) -> None:
        self.violations = violations
        super().__init__("; ".join(f"{v.rule_id}: {v.message}" for v in violations))

    @property
    def rule_ids(self) -> list[str]:
        return [v.rule_id for v in self.violations]


class AttemptNotFoundError(LookupError):
    """No such attempt for this student — missing, or owned by someone else.

    Deliberately one error for both: distinguishing them would tell a caller
    that an attempt it cannot touch exists (§19).
    """


# --- Validation -------------------------------------------------------------


@dataclass
class _Checked:
    """A validated submission: the paper, its sub-parts, and coerced entries."""

    paper: Paper
    sub_parts: dict[int, SubPart]
    entries: list[tuple[SubPart, int, str]] = field(default_factory=list)

    @property
    def total_marks(self) -> int:
        return sum(sp.max_marks for sp in self.sub_parts.values())


def _coerce_marks_lost(value: object) -> int | None:
    """Whole numbers only (RP-V-007). None when it isn't one.

    Accepts the int the service contract types, and the string/Decimal a form
    post arrives as, as long as it denotes a whole number. `True`/`False` are
    ints in Python but never a mark, so they are refused.
    """
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    try:
        as_decimal = Decimal(str(value).strip())
    except (InvalidOperation, ValueError, TypeError):
        return None
    if as_decimal != as_decimal.to_integral_value():
        return None
    return int(as_decimal)


def _paper_sub_parts(db: Session, paper_id: int) -> dict[int, SubPart]:
    rows = db.scalars(
        select(SubPart)
        .join(SubPart.question)
        .where(SubPart.question.has(paper_id=paper_id))
        .order_by(SubPart.sort_order, SubPart.id)
    ).all()
    return {sp.id: sp for sp in rows}


def _validate(
    db: Session,
    paper_id: int | None,
    date_completed: date | None,
    entries: list[SubPartEntry],
) -> _Checked:
    """Collect every violation in the submission, then raise once.

    Nothing short-circuits: a submission with a bad date AND four bad rows
    reports all five, so the form can mark them together.
    """
    violations: list[Violation] = []

    # RP-V-001 — the submission must identify a real paper and a date. Level,
    # session and variant are attributes OF the paper, so a resolvable
    # paper_id is how this service sees those fields.
    paper = db.get(Paper, paper_id) if paper_id is not None else None
    if paper_id is None:
        violations.append(Violation("RP-V-001", "Paper is required."))
    elif paper is None:
        violations.append(Violation("RP-V-001", f"Unknown paper {paper_id!r}."))

    if date_completed is None:
        violations.append(Violation("RP-V-001", "Date Completed is required."))
    elif not isinstance(date_completed, date):
        violations.append(Violation("RP-V-001", "Date Completed must be a date."))

    sub_parts = _paper_sub_parts(db, paper.id) if paper is not None else {}
    checked = _Checked(paper=paper, sub_parts=sub_parts)  # type: ignore[arg-type]

    seen: set[int] = set()
    for entry in entries:
        sub_part = sub_parts.get(entry.sub_part_id)
        if sub_part is None:
            # Only meaningful once the paper resolved; otherwise every row
            # would repeat the RP-V-001 failure above.
            if paper is not None:
                violations.append(
                    Violation(
                        "RP-V-001",
                        f"Sub-part {entry.sub_part_id} is not part of this paper.",
                        entry.sub_part_id,
                    )
                )
            continue

        # RP-V-011 — the same row twice would collide on
        # UNIQUE(attempt_id, sub_part_id) at flush; caught here so it reports
        # as a rule rather than an IntegrityError.
        if sub_part.id in seen:
            violations.append(
                Violation("RP-V-011", "This sub-part appears more than once.", sub_part.id)
            )
            continue
        seen.add(sub_part.id)

        marks_lost = _coerce_marks_lost(entry.marks_lost)
        if entry.marks_lost is None or entry.marks_lost == "":
            violations.append(Violation("RP-V-004", "Marks Lost is required.", sub_part.id))
            continue
        if marks_lost is None:
            violations.append(
                Violation("RP-V-007", "Marks Lost must be a whole number.", sub_part.id)
            )
            continue
        if marks_lost < 0:
            violations.append(Violation("RP-V-005", "Marks Lost cannot be negative.", sub_part.id))
            continue
        if marks_lost > sub_part.max_marks:
            violations.append(
                Violation(
                    "RP-V-006",
                    f"Marks Lost {marks_lost} exceeds this row's Max Marks ({sub_part.max_marks}).",
                    sub_part.id,
                )
            )
            continue

        error_type = (entry.error_type or "").strip()
        if error_type not in ERROR_TYPES:
            # A UI lock is not validation — the service owns the controlled set.
            violations.append(
                Violation(
                    "RP-V-008" if marks_lost == 0 else "RP-V-009",
                    f"Error Type {entry.error_type!r} is not one of the nine allowed values.",
                    sub_part.id,
                )
            )
        elif marks_lost == 0 and error_type != NO_ERROR:
            violations.append(
                Violation(
                    "RP-V-008",
                    f'Marks Lost 0 must be recorded as "{NO_ERROR}", not {error_type!r}.',
                    sub_part.id,
                )
            )
        elif marks_lost > 0 and error_type == NO_ERROR:
            violations.append(
                Violation(
                    "RP-V-009",
                    f'Marks Lost {marks_lost} cannot be "{NO_ERROR}" — choose the error category.',
                    sub_part.id,
                )
            )
        else:
            checked.entries.append((sub_part, marks_lost, error_type))

    # RP-V-004 — a sub-part with no row at all is a blank row. Reported after
    # the loop so the message names every one of them.
    if paper is not None:
        missing = [sp for sub_part_id, sp in sub_parts.items() if sub_part_id not in seen]
        for sub_part in missing:
            violations.append(
                Violation("RP-V-004", "Marks Lost is required (no row submitted).", sub_part.id)
            )

    # RP-V-010 — the ceiling is the paper's OWN stated mark scale
    # (papers.total_marks, 75 for every seeded MVP paper), never a hard-coded
    # 75. Checked on the rows that passed, so one absurd row reports as
    # RP-V-006 rather than twice.
    if paper is not None:
        total_lost = sum(marks_lost for _, marks_lost, _ in checked.entries)
        if total_lost > paper.total_marks:
            violations.append(
                Violation(
                    "RP-V-010",
                    f"Total Marks Lost {total_lost} exceeds the paper "
                    f"total of {paper.total_marks}.",
                )
            )

    if violations:
        raise RecordValidationError(violations)

    return checked


# --- Edit-mode read (BRD §11) -----------------------------------------------
#
# Opening a saved attempt pre-populates the form. This is the inverse of
# `_write_results`' conversion: the schema stores marks_scored, the form shows
# MARKS LOST, so `marks_lost = max_marks - marks_scored`. Read-only, and gated
# by the same ownership guard as the write path (§19) — a student can only
# re-open an attempt that is their own.


@dataclass
class AttemptForEdit:
    """A saved attempt reshaped for the Record form (BRD §11).

    `level`, `component`, `session_key` and `variant` are the Paper Details the
    page re-resolves the selection cascade from; `marks_lost` and `error_type`
    are keyed by sub_part_id so the page can pre-fill each row.
    """

    attempt_id: int
    paper_id: int
    level: str
    component: int
    session_key: str
    variant: int
    date_completed: date | None
    marks_lost: dict[int, int] = field(default_factory=dict)
    error_type: dict[int, str] = field(default_factory=dict)


def load_attempt_for_edit(db: Session, student_id: int, attempt_id: int) -> AttemptForEdit:
    """The student's own saved attempt, reshaped for the form, or raises.

    Raises AttemptNotFoundError for a missing attempt OR one owned by someone
    else — the same one error for both, so the caller cannot tell them apart
    (§19). The stored marks_scored are converted back to marks lost here, the
    single inverse of the write path's conversion.
    """
    attempt = _load_owned_attempt(db, attempt_id, student_id)
    paper = attempt.paper
    sub_parts = _paper_sub_parts(db, paper.id)

    marks_lost: dict[int, int] = {}
    error_type: dict[int, str] = {}
    for result in attempt.results:
        sub_part = sub_parts.get(result.sub_part_id)
        if sub_part is None:
            continue  # a result whose sub-part left the paper — nothing to show
        marks_lost[result.sub_part_id] = sub_part.max_marks - result.marks_scored
        error_type[result.sub_part_id] = result.error_type or NO_ERROR

    return AttemptForEdit(
        attempt_id=attempt.id,
        paper_id=paper.id,
        level=paper.level,
        component=paper.component,
        # Mirrors SessionOption.key in paper_catalog, so resolve_selection can
        # round-trip it back to the same paper.
        session_key=f"{paper.session.name}-{paper.year}",
        variant=paper.variant,
        date_completed=attempt.date_completed,
        marks_lost=marks_lost,
        error_type=error_type,
    )


# --- Persistence ------------------------------------------------------------


def _load_owned_attempt(db: Session, attempt_id: int, student_id: int) -> Attempt:
    """The student's own attempt, or AttemptNotFoundError (§19, RP-V-012)."""
    attempt = db.get(Attempt, attempt_id)
    if attempt is None or attempt.student_id != student_id:
        raise AttemptNotFoundError(f"No attempt {attempt_id} for student {student_id}.")
    return attempt


def _as_completed_at(date_completed: date) -> datetime:
    """The stated date as the timestamp the analytics views order by.

    `v_latest_paper_attempts` picks the counted attempt with
    `ORDER BY completed_at DESC NULLS LAST`, so leaving completed_at NULL here
    would make a freshly recorded attempt sort OLDEST — the newest result would
    be ignored by every engine. Midnight UTC on the stated date keeps the two
    columns telling the same story.
    """
    return datetime.combine(date_completed, time.min, tzinfo=UTC)


def _write_results(db: Session, attempt: Attempt, checked: _Checked) -> None:
    """Upsert one result row per entry, converting marks lost → marks scored.

    THE CONVERSION lives here and nowhere else.
    """
    existing = {r.sub_part_id: r for r in attempt.results}

    for sub_part, marks_lost, error_type in checked.entries:
        marks_scored = sub_part.max_marks - marks_lost  # <- THE CONVERSION

        result = existing.get(sub_part.id)
        if result is None:
            db.add(
                SubPartResult(
                    attempt_id=attempt.id,
                    sub_part_id=sub_part.id,
                    marks_scored=marks_scored,
                    error_type=error_type,
                )
            )
        else:
            result.marks_scored = marks_scored
            result.error_type = error_type


def save_attempt(
    db: Session,
    student_id: int,
    paper_id: int | None,
    date_completed: date | None,
    entries: list[SubPartEntry],
    attempt_id: int | None = None,
) -> RecordResult:
    """Record a completed practice paper, or correct one already recorded.

    `attempt_id is None` creates exactly one new attempt (RP-F-001).
    `attempt_id` set updates THAT attempt in place (RP-F-005/006) — the
    completed-attempt count does not change (RP-T-015).

    Raises RecordValidationError with every §12 violation collected, or
    AttemptNotFoundError when editing an attempt that isn't this student's.
    """
    checked = _validate(db, paper_id, date_completed, entries)
    assert date_completed is not None  # _validate rejects None

    if attempt_id is None:
        attempt = Attempt(
            student_id=student_id,
            paper_id=checked.paper.id,
            status=AttemptStatus.COMPLETED,
            date_completed=date_completed,
            completed_at=_as_completed_at(date_completed),
        )
        db.add(attempt)
        db.flush()  # assigns attempt.id for the result rows
    else:
        attempt = _load_owned_attempt(db, attempt_id, student_id)
        if attempt.paper_id != checked.paper.id:
            # Re-pointing an attempt at a different paper would orphan every
            # result row against the old paper's sub-parts. Correcting the
            # paper choice means recording the right paper, not mutating this
            # one (BRD §32 rule 7 is about not duplicating, not re-labelling).
            raise RecordValidationError(
                [
                    Violation(
                        "RP-V-001",
                        "The paper cannot be changed when editing an attempt.",
                    )
                ]
            )
        attempt.status = AttemptStatus.COMPLETED
        attempt.date_completed = date_completed
        attempt.completed_at = _as_completed_at(date_completed)

    _write_results(db, attempt, checked)
    db.commit()

    # §14 — every figure derived here, none accepted from the client.
    total_marks = checked.total_marks
    total_marks_lost = sum(marks_lost for _, marks_lost, _ in checked.entries)
    total_score = total_marks - total_marks_lost

    return RecordResult(
        attempt_id=attempt.id,
        total_marks=total_marks,
        total_marks_lost=total_marks_lost,
        total_score=total_score,
        percentage=round(100.0 * total_score / total_marks, PERCENTAGE_DIGITS),
    )


# --- Live Results Summary preview (BRD §9, §14) -----------------------------
#
# The Record page recalculates the four result metrics as the student types,
# BEFORE anything is saved (BRD §14/§15: "All displayed result values must
# update when a Marks Lost value changes"). This is a PREVIEW, not the save
# path: a half-filled table must still show an honest running total, so a
# blank, non-numeric or out-of-range entry counts as 0 here rather than
# raising. The authoritative validation is `save_attempt`; the two share
# `_coerce_marks_lost` and PERCENTAGE_DIGITS so the previewed number is the
# number that will be stored.


@dataclass
class ResultsSummary:
    """The four read-only figures of BRD §9's Results Summary."""

    total_marks: int
    total_marks_lost: int
    total_score: int
    percentage: float


def summarise_marks_lost(
    caps: list[tuple[int, int]], marks_lost: dict[int, object]
) -> ResultsSummary:
    """Total Marks / Marks Lost / Score / Percentage for a partly-filled form.

    `caps` is the paper's (sub_part_id, max_marks) pairs from the question
    database — the denominator is summed from them (§14: never a hard-coded
    75). `marks_lost` maps sub_part_id to the raw submitted value. Each entry
    is coerced and clamped to 0..max_marks; anything else contributes 0, so the
    preview never exceeds the scale and never raises mid-entry.
    """
    total_marks = 0
    total_lost = 0
    for sub_part_id, max_marks in caps:
        total_marks += max_marks
        value = _coerce_marks_lost(marks_lost.get(sub_part_id))
        if value is None or value < 0:
            value = 0
        elif value > max_marks:
            value = max_marks
        total_lost += value

    total_score = total_marks - total_lost
    percentage = round(100.0 * total_score / total_marks, PERCENTAGE_DIGITS) if total_marks else 0.0
    return ResultsSummary(
        total_marks=total_marks,
        total_marks_lost=total_lost,
        total_score=total_score,
        percentage=percentage,
    )
