from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models import Student
from app.services.overview import build_family_overview

router = APIRouter()
templates = Jinja2Templates(directory="app/web/templates")

STUDENT_ID = 1
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


PRIORITY_CLASSES = {
    "High": "bg-rose-50 text-rose-700 border-rose-200",
    "Medium": "bg-amber-50 text-amber-700 border-amber-200",
    "Monitor": "bg-slate-100 text-slate-600 border-slate-200",
}

TREND_PILL_CLASSES = {
    "Improving": "bg-emerald-50 text-emerald-700",
    "Stable": "bg-slate-100 text-slate-600",
    "Needs Focus": "bg-rose-50 text-rose-700",
    "More data needed": "bg-slate-100 text-slate-400",
}

templates.env.filters["band"] = performance_band
templates.env.globals["priority_classes"] = PRIORITY_CLASSES
templates.env.globals["trend_pill_classes"] = TREND_PILL_CLASSES


@router.get("/overview")
def overview(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    level: str | None = None,
):
    student = db.scalar(select(Student).where(Student.id == STUDENT_ID))
    student_name = student.display_name if student else "Unknown Student"
    default_level = student.level if student else "AS"
    exam_level = level if level in ALLOWED_LEVELS else default_level

    panels = [
        {
            "family": family,
            "label": FAMILY_LABELS[family],
            "overview": build_family_overview(db, STUDENT_ID, exam_level, family),
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
        },
    )
