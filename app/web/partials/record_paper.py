"""HTML fragments for the Record Practice Paper selection chain (BRD §6, §15).

The first HTMX fragment endpoint in the app, so it sets the convention
CLAUDE.md's architecture asks for: full pages in `app/web/routes/`, swap
fragments here.

One endpoint serves the whole cascade. Every select in the chain — Level,
Paper Type, Session, Variant — fires the same GET with all five field values
included, and gets back the three dependent dropdowns rebuilt from the
database. §6's "changing Level clears incompatible Paper Type, Session and
Variant selections and reloads the valid choices" is therefore decided in one
place (`resolve_selection`) rather than spread across four handlers that could
drift apart.
"""

from typing import Annotated
from urllib.parse import parse_qsl

from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.core.auth import CurrentStudent
from app.core.db import get_db
from app.services.paper_catalog import (
    LEVELS,
    question_rows,
    resolve_selection,
    variant_code,
)
from app.services.record import ERROR_TYPES, summarise_marks_lost

router = APIRouter()
templates = Jinja2Templates(directory="app/web/templates")
templates.env.globals["error_types"] = ERROR_TYPES
templates.env.globals["variant_code"] = variant_code


@router.get("/record/paper-options")
def paper_options(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    student: CurrentStudent,
    level: str | None = None,
    component: str | None = None,
    session: str | None = None,
    variant: str | None = None,
):
    """Rebuild the dependent dropdowns for the submitted selection.

    Protected like the page it belongs to (§19). `student` is unused here —
    the paper catalogue is reference data, not student data — but an
    unauthenticated caller must not reach a fragment of a protected page.

    An unknown `level` falls back to the first valid one rather than erroring:
    the value comes from a select whose options the server itself rendered, so
    anything else is a tampered request, and the honest answer is the options
    for a real level, not a 500.
    """
    exam_level = level if level in LEVELS else LEVELS[0]
    selection = resolve_selection(db, exam_level, component, session, variant)

    rows = question_rows(db, selection.paper.id) if selection.is_complete else []
    summary = (
        summarise_marks_lost([(r.sub_part_id, r.max_marks) for r in rows], {}) if rows else None
    )

    return templates.TemplateResponse(
        request,
        "partials/paper_options_response.html",
        {"selection": selection, "rows": rows, "summary": summary},
    )


@router.post("/record/summary")
async def record_summary(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    student: CurrentStudent,
):
    """Recompute the four Results Summary figures for the submitted marks lost.

    Protected like its page (§19); `student` is unused because the paper's
    structure is reference data, not student data. The form carries `paper_id`
    plus one `marks_lost_<sub_part_id>` per row; a missing, blank or invalid
    entry counts as 0 (`summarise_marks_lost`), so a half-filled table still
    totals honestly. Nothing is persisted.
    """
    # Parsed by hand rather than via request.form()/Form(...): both need
    # python-multipart, which is deliberately not a dependency (same reason as
    # app/web/routes/auth.py). The marks form is url-encoded with one unique
    # marks_lost_<id> key per row, so a flat dict is the whole payload.
    body = (await request.body()).decode("utf-8", errors="replace")
    form = dict(parse_qsl(body, keep_blank_values=True))

    try:
        paper_id = int(form.get("paper_id", ""))
    except (TypeError, ValueError):
        paper_id = None

    rows = question_rows(db, paper_id) if paper_id is not None else []
    marks_lost = {row.sub_part_id: form.get(f"marks_lost_{row.sub_part_id}") for row in rows}
    summary = summarise_marks_lost([(r.sub_part_id, r.max_marks) for r in rows], marks_lost)

    return templates.TemplateResponse(
        request,
        "partials/results_summary.html",
        {"summary": summary},
    )
