"""Record Practice Paper page (BRD §5, §6, §7, §10, §11, §12, §16, §18).

Full-page routes: the shell + Paper Details cascade (GET /record), the same
page pre-populated from a saved attempt (GET /record/{attempt_id}/edit), and
the save/update action (POST /record). The HTMX fragments that drive the
cascade and the live Results Summary live in `app.web.partials.record_paper`,
per CLAUDE.md's split between pages and fragments.

The write path is NOT reimplemented here (§16): this route parses the form,
calls `app.services.record.save_attempt`, and turns its result into a redirect
or a re-rendered form. All validation is the service's (§12); the client-side
min/max guards in the template are UX on top of it, never a substitute.

Security (§19, login-auth): every route is protected by `CurrentStudent`, so
`student_id` comes from the signed session cookie and from nowhere else — never
the form. A posted student_id would simply be ignored.
"""

from datetime import date
from typing import Annotated
from urllib.parse import parse_qsl

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.core.auth import CurrentStudent
from app.core.db import get_db
from app.models import Paper
from app.services.paper_catalog import (
    LEVELS,
    parse_int,
    question_rows,
    resolve_selection,
    variant_code,
)
from app.services.record import (
    ERROR_TYPES,
    AttemptNotFoundError,
    RecordValidationError,
    SubPartEntry,
    Violation,
    load_attempt_for_edit,
    save_attempt,
    summarise_marks_lost,
)

router = APIRouter()
templates = Jinja2Templates(directory="app/web/templates")

# Imported Jinja macros do not see the calling template's context, so the level
# list is registered as a global rather than passed per-render. It is still the
# one definition in app.services.paper_catalog — never a literal in a template.
templates.env.globals["levels"] = LEVELS
templates.env.globals["error_types"] = ERROR_TYPES
templates.env.globals["variant_code"] = variant_code

# Where a successful save lands: Overview, so the new/updated attempt is
# reflected in the analytics the moment the browser re-requests it (§10, §16;
# RP-F-007 — analytics are computed on read, no recalculate step).
AFTER_SAVE_URL = "/overview"


def student_initials(display_name: str) -> str:
    parts = display_name.split()
    return "".join(p[0] for p in parts[:2]).upper()


async def _urlencoded_body(request: Request) -> dict[str, str]:
    """Parse an application/x-www-form-urlencoded body.

    Same reason as auth.py and overview.py: FastAPI's Form(...) and Starlette's
    request.form() both need python-multipart, which is deliberately not a
    dependency (CLAUDE.md: ask before adding one). The record form posts
    urlencoded, so a stdlib parse is the whole payload.
    """
    body = (await request.body()).decode("utf-8", errors="replace")
    return dict(parse_qsl(body, keep_blank_values=True))


def _parse_date(raw: str | None) -> date | None:
    """A "YYYY-MM-DD" form value as a date, or None.

    None flows through to the service as a missing Date Completed (RP-V-001);
    an unparseable value is treated the same way rather than raising in the
    route — the service owns the "date required" message.
    """
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def _entries_from_form(form: dict[str, str]) -> list[SubPartEntry]:
    """Build one SubPartEntry per row the form carries.

    Each row posts `marks_lost_<sub_part_id>` and `error_type_<sub_part_id>`.
    Values are passed through as the raw strings a form yields — the service's
    `_coerce_marks_lost` and its §12 checks are the authoritative validator, so
    a blank ("") reaches it as the RP-V-004 case rather than being silently
    fixed up here.
    """
    entries: list[SubPartEntry] = []
    for key, value in form.items():
        if not key.startswith("marks_lost_"):
            continue
        sub_part_id = parse_int(key[len("marks_lost_") :])
        if sub_part_id is None:
            continue
        entries.append(
            SubPartEntry(
                sub_part_id=sub_part_id,
                marks_lost=value,  # type: ignore[arg-type]  # service coerces the form string
                error_type=form.get(f"error_type_{sub_part_id}", ""),
            )
        )
    return entries


def _selection_from_form(db: Session, form: dict[str, str]):
    """Rebuild the paper selection for a re-render after a rejected save.

    Prefers the posted `paper_id` — it names the exact paper unambiguously — and
    derives the cascade params from it, so the dropdowns and table come back
    even if only the hidden paper_id reached us. Falls back to the posted Paper
    Details fields when no paper resolves, so an incomplete selection still
    round-trips its dropdowns.
    """
    paper = db.get(Paper, parse_int(form.get("paper_id")) or 0)
    if paper is not None:
        return resolve_selection(
            db,
            paper.level,
            str(paper.component),
            f"{paper.session.name}-{paper.year}",
            str(paper.variant),
        )
    return resolve_selection(
        db, form.get("level"), form.get("component"), form.get("session"), form.get("variant")
    )


def _prefill_from_form(form: dict[str, str]) -> dict[int, dict[str, str]]:
    """The submitted per-row values, so a rejected save keeps them all (§18)."""
    prefill: dict[int, dict[str, str]] = {}
    for key, value in form.items():
        if key.startswith("marks_lost_"):
            sub_part_id = parse_int(key[len("marks_lost_") :])
            field = "marks_lost"
        elif key.startswith("error_type_"):
            sub_part_id = parse_int(key[len("error_type_") :])
            field = "error_type"
        else:
            continue
        if sub_part_id is not None:
            prefill.setdefault(sub_part_id, {})[field] = value
    return prefill


def _render(
    request: Request,
    db: Session,
    student: CurrentStudent,
    *,
    exam_level: str,
    selection,
    date_completed: str,
    attempt_id: int | None = None,
    prefill: dict[int, dict[str, str]] | None = None,
    violations: list[Violation] | None = None,
    status_code: int = 200,
):
    """Render record.html for every state: new form, edit, or rejected save.

    `prefill` maps sub_part_id -> {marks_lost, error_type} for edit mode and for
    retaining a rejected submission (§18: never clear the form). `violations`
    are the service's §12 failures; those with a sub_part_id flag their row,
    the rest surface as a form-level banner. The Results Summary is recomputed
    from whatever marks are on the form, so it stays honest on a re-render too.
    """
    prefill = prefill or {}
    violations = violations or []

    rows = question_rows(db, selection.paper.id) if selection.is_complete else []
    if rows:
        marks_lost = {
            row.sub_part_id: prefill.get(row.sub_part_id, {}).get("marks_lost") for row in rows
        }
        summary = summarise_marks_lost([(r.sub_part_id, r.max_marks) for r in rows], marks_lost)
    else:
        summary = None

    row_errors = {v.sub_part_id for v in violations if v.sub_part_id is not None}
    form_errors = [v.message for v in violations if v.sub_part_id is None]

    return templates.TemplateResponse(
        request,
        "record.html",
        {
            "active_nav": "record",
            "student_name": student.display_name,
            "student_initials": student_initials(student.display_name),
            "exam_level": exam_level,
            "selection": selection,
            "rows": rows,
            "summary": summary,
            "date_completed": date_completed,
            "attempt_id": attempt_id,
            "prefill": prefill,
            "row_errors": row_errors,
            "form_errors": form_errors,
        },
        status_code=status_code,
    )


@router.get("/record")
def record_page(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    student: CurrentStudent,
    level: str | None = None,
):
    """Render the page with the cascade at its starting point.

    Two different levels are in play and the BRD keeps them apart (§5): the
    shell's `exam_level` context (the AS/A toggle) and `selection.level`, the
    level OF THE PAPER BEING RECORDED. Both start from the same value; the
    latter then moves independently as the student uses the Level dropdown.
    """
    exam_level = level if level in LEVELS else student.level

    return _render(
        request,
        db,
        student,
        exam_level=exam_level,
        selection=resolve_selection(db, exam_level),
        # §6 requires a date but names no default; an unset picker is the honest
        # starting state rather than guessing at "today".
        date_completed="",
    )


@router.get("/record/{attempt_id}/edit")
def edit_record_page(
    attempt_id: int,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    student: CurrentStudent,
):
    """Open a saved attempt for correction, pre-populated (§11).

    Ownership is the service's to enforce (§19): a missing attempt and one that
    belongs to another student both raise AttemptNotFoundError, which becomes a
    404 here — the page never confirms that an attempt it cannot touch exists.
    """
    try:
        data = load_attempt_for_edit(db, student.id, attempt_id)
    except AttemptNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Attempt not found") from exc

    selection = resolve_selection(
        db, data.level, str(data.component), data.session_key, str(data.variant)
    )
    prefill = {
        sub_part_id: {
            "marks_lost": str(data.marks_lost.get(sub_part_id, "")),
            "error_type": data.error_type.get(sub_part_id, ""),
        }
        for sub_part_id in data.marks_lost
    }

    return _render(
        request,
        db,
        student,
        # The shell context follows the paper's own level when editing.
        exam_level=data.level if data.level in LEVELS else student.level,
        selection=selection,
        date_completed=data.date_completed.isoformat() if data.date_completed else "",
        attempt_id=data.attempt_id,
        prefill=prefill,
    )


@router.post("/record")
async def save_record(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    student: CurrentStudent,
):
    """Save a new attempt, or update the one named by `attempt_id` (§10, §16).

    `attempt_id` absent -> create exactly one attempt (RP-F-001). `attempt_id`
    present -> update THAT attempt in place, never a duplicate (RP-F-005/006,
    RP-T-015). On success, redirect to Overview (POST/redirect/GET) so the new
    data is live in the analytics. On a §12 failure, re-render the form with
    every violation flagged at once and all entered values kept (§12, §18).
    """
    form = await _urlencoded_body(request)
    attempt_id = parse_int(form.get("attempt_id"))
    paper_id = parse_int(form.get("paper_id"))
    date_completed = _parse_date(form.get("date_completed"))

    try:
        save_attempt(
            db,
            student_id=student.id,
            paper_id=paper_id,
            date_completed=date_completed,
            entries=_entries_from_form(form),
            attempt_id=attempt_id,
        )
    except AttemptNotFoundError as exc:
        # Editing an attempt that isn't this student's, or doesn't exist (§19).
        raise HTTPException(status_code=404, detail="Attempt not found") from exc
    except RecordValidationError as exc:
        # Rebuild the same paper and its table so the violations can be shown on
        # the rows, then re-render with every entered value kept (§18).
        selection = _selection_from_form(db, form)
        exam_level = selection.level if selection.level in LEVELS else student.level
        return _render(
            request,
            db,
            student,
            exam_level=exam_level,
            selection=selection,
            date_completed=form.get("date_completed", ""),
            attempt_id=attempt_id,
            prefill=_prefill_from_form(form),
            violations=exc.violations,
            status_code=400,
        )

    return RedirectResponse(url=AFTER_SAVE_URL, status_code=303)
