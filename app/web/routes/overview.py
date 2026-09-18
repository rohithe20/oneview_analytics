from typing import Annotated
from urllib.parse import parse_qsl

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.core.auth import CurrentStudent
from app.core.db import get_db
from app.models import Student
from app.services.overview import build_family_overview
from app.services.planning import TargetValidationError, set_target

router = APIRouter()
templates = Jinja2Templates(directory="app/web/templates")

ALLOWED_LEVELS = {"AS", "A"}
FAMILIES = ["Pure", "Statistics"]
FAMILY_LABELS = {"Pure": "Pure Mathematics", "Statistics": "Statistics"}


def student_initials(display_name: str) -> str:
    parts = display_name.split()
    return "".join(p[0] for p in parts[:2]).upper()


def performance_band(pct: float | None) -> str:
    """Strong/moderate/weak colour band per overview-ui.md §2."""
    if pct is None:
        return "slate"
    if pct >= 75:
        return "emerald"
    if pct >= 50:
        return "amber"
    return "rose"


def format_percentage(pct: float | None) -> str:
    """Display-only: one decimal at most, trailing '.0' dropped (75.33 -> '75.3%')."""
    if pct is None:
        return "—"
    rounded = round(float(pct), 1)
    text = str(int(rounded)) if rounded == int(rounded) else f"{rounded:.1f}"
    return f"{text}%"


def format_marks(value: float | None) -> str:
    """Display-only: marks to one decimal, trailing '.0' dropped (mark-scale.md)."""
    if value is None:
        return "—"
    rounded = round(float(value), 1)
    return str(int(rounded)) if rounded == int(rounded) else f"{rounded:.1f}"


def format_marks_nearest(value: float | None) -> str:
    """Display-only: nearest whole mark, for the predicted range ("64 - 68 / 75")."""
    if value is None:
        return "—"
    return str(round(float(value)))


PRIORITY_CLASSES = {
    "High": "bg-rose-50 text-rose-700 border-rose-200",
    "Medium": "bg-amber-50 text-amber-700 border-amber-200",
    "Monitor": "bg-slate-100 text-slate-600 border-slate-200",
}

TREND_PILL_CLASSES = {
    "Improving": "bg-emerald-50 text-emerald-700",
    "Stable": "bg-amber-50 text-amber-700",
    "Needs Focus": "bg-rose-50 text-rose-700",
    "More data needed": "bg-slate-100 text-slate-400",
}

TREND_TEXT_CLASSES = {
    "Improving": "text-emerald-600",
    "Stable": "text-amber-600",
    "Needs Focus": "text-rose-600",
    "More data needed": "text-slate-400",
}

templates.env.filters["band"] = performance_band
templates.env.filters["pct"] = format_percentage
templates.env.filters["marks"] = format_marks
templates.env.filters["marks_nearest"] = format_marks_nearest
templates.env.globals["priority_classes"] = PRIORITY_CLASSES
templates.env.globals["trend_pill_classes"] = TREND_PILL_CLASSES
templates.env.globals["trend_text_classes"] = TREND_TEXT_CLASSES


def _render_overview(
    request: Request,
    db: Session,
    student: Student,
    exam_level: str,
    target_error: dict | None = None,
    status_code: int = 200,
):
    """Render the Overview for ONE student — the logged-in one.

    `student` arrives from the session via get_current_student, never from the
    request, so the scope filter (student_id, exam_level, component_family)
    can only ever address the caller's own data.
    """
    student_name = student.display_name

    panels = [
        {
            "family": family,
            "label": FAMILY_LABELS[family],
            "overview": build_family_overview(db, student.id, exam_level, family),
        }
        for family in FAMILIES
    ]

    return templates.TemplateResponse(
        request,
        "overview.html",
        {
            "active_nav": "overview",
            "student_name": student_name,
            "student_initials": student_initials(student_name),
            "exam_level": exam_level,
            "panels": panels,
            # {"family": ..., "message": ...} — re-opens that panel's Edit
            # Target form with the rejected value explained.
            "target_error": target_error,
        },
        status_code=status_code,
    )


@router.get("/overview")
def overview(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    student: CurrentStudent,
    level: str | None = None,
):
    """`level` is the only scope dimension the request may choose.

    It selects AS or A within the caller's own data; student_id is fixed by
    the session. An unrecognised value falls back to the student's own level
    rather than erroring.
    """
    exam_level = level if level in ALLOWED_LEVELS else student.level

    return _render_overview(request, db, student, exam_level)


async def _urlencoded_body(request: Request) -> dict[str, str]:
    """Parse an application/x-www-form-urlencoded body.

    FastAPI's Form(...) and Starlette's request.form() both require
    python-multipart, which is not a dependency of this project (CLAUDE.md:
    ask before adding one). HTML forms post urlencoded by default, and that
    format is a stdlib parse — so this route does it directly.
    """
    body = (await request.body()).decode("utf-8", errors="replace")
    return dict(parse_qsl(body, keep_blank_values=True))


@router.post("/overview/target")
async def update_target(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    student: CurrentStudent,
):
    """Set the practice target for one (level, family) scope — D2 / OV-PL-003.

    The form carries level and family; the student it belongs to comes from
    the session, so a posted student_id would be ignored even if one were sent.
    """
    form = await _urlencoded_body(request)
    level = form.get("level")
    family = form.get("family")

    if level not in ALLOWED_LEVELS or family not in FAMILIES:
        raise HTTPException(status_code=404, detail="Unknown scope")

    try:
        value = int(form.get("target_value", ""))
    except (TypeError, ValueError):
        return _render_overview(
            request,
            db,
            student,
            level,
            target_error={"family": family, "message": "Enter a whole number of papers."},
            status_code=400,
        )

    try:
        set_target(db, student.id, level, family, value)
    except TargetValidationError as exc:
        return _render_overview(
            request,
            db,
            student,
            level,
            target_error={"family": family, "message": str(exc)},
            status_code=400,
        )

    # POST/redirect/GET: the target is stored, the page re-reads it.
    return RedirectResponse(url=f"/overview?level={level}", status_code=303)
