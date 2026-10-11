"""Topic Analysis page (docs/specs/topic-analysis-ui.md).

Read-only diagnostic drill-down. Two routes, both protected by CurrentStudent
so `student_id` comes from the signed session and never the request (the scope
invariant, BRD §32):

- GET /topic-analysis            — the full page (shell + tiles + workspace).
- GET /topic-analysis/workspace  — just the workspace region (the two tables and
  the question panel), for the HTMX row-selection swap. Clicking a topic re-
  defaults its weakest subtopic and refreshes the question panel; clicking a
  subtopic refreshes only the panel. Both swap #ta-workspace.

The template holds NO logic (§4): it renders the TopicAnalysisView that
app.services.topic_analysis.build_topic_analysis assembles for one scope. The
`level` and `family` query params are the only scope dimensions the request may
choose; both fall back to a safe default rather than erroring, mirroring
Overview.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import CurrentStudent
from app.core.db import get_db
from app.models import Student, Topic
from app.services.priority import STATUS_INSUFFICIENT
from app.services.topic_analysis import build_topic_analysis
from app.web.routes.overview import (
    format_marks,
    format_percentage,
    performance_band,
    student_initials,
)

router = APIRouter()
templates = Jinja2Templates(directory="app/web/templates")

ALLOWED_LEVELS = {"AS", "A"}
FAMILIES = {"Pure", "Statistics"}
FAMILY_LABELS = {"Pure": "Pure Mathematics", "Statistics": "Statistics"}

# Status pill colours (topic-analysis-ui.md §6): Strong emerald, Monitor slate,
# Needs Focus deeper amber, High Priority rose, Insufficient data muted slate.
# These are the labels classify_status emits — one place, so both tables agree.
STATUS_CLASSES = {
    "Strong": "bg-emerald-50 text-emerald-700 border-emerald-200",
    "Monitor": "bg-slate-100 text-slate-600 border-slate-200",
    "Needs Focus": "bg-amber-100 text-amber-800 border-amber-200",
    "High Priority": "bg-rose-50 text-rose-700 border-rose-200",
    STATUS_INSUFFICIENT: "bg-slate-50 text-slate-400 border-slate-200",
}

# Reuse Overview's display filters verbatim — same numbers, same formatting, so
# the two screens can never render the same value differently.
templates.env.filters["band"] = performance_band
templates.env.filters["pct"] = format_percentage
templates.env.filters["marks"] = format_marks
templates.env.globals["status_classes"] = STATUS_CLASSES


def _resolve_topic_id(db: Session, family_topic_name: str | None) -> int | None:
    """Map a top-level topic NAME to its id, or None.

    Overview's Priority-Areas links carry the topic name (?topic=Integration);
    the HTMX rows carry the numeric id. This accepts the name form so those
    deep-links land on the right topic without the caller knowing the id.
    """
    if not family_topic_name:
        return None
    return db.scalar(
        select(Topic.id).where(Topic.name == family_topic_name, Topic.parent_id.is_(None))
    )


def _build(
    db: Session,
    student: Student,
    level: str | None,
    family: str | None,
    topic_id: int | None,
    topic: str | None,
    subtopic_id: int | None,
):
    """Resolve the scope + selection and assemble the view — shared by both routes."""
    exam_level = level if level in ALLOWED_LEVELS else student.level
    component_family = family if family in FAMILIES else "Pure"

    # A numeric topic_id (from an HTMX row) wins; else a topic NAME (from an
    # Overview deep-link) is resolved to its id; else None -> priority default.
    selected_topic_id = topic_id if topic_id is not None else _resolve_topic_id(db, topic)

    view = build_topic_analysis(
        db,
        student.id,
        exam_level,
        component_family,
        selected_topic_id=selected_topic_id,
        selected_subtopic_id=subtopic_id,
    )
    return exam_level, component_family, view


def _context(student: Student, exam_level: str, component_family: str, view) -> dict:
    return {
        "active_nav": "topic-analysis",
        "student_name": student.display_name,
        "student_initials": student_initials(student.display_name),
        "exam_level": exam_level,
        "component_family": component_family,
        "family_label": FAMILY_LABELS[component_family],
        "view": view,
        # The shell's AS/A toggle must reload THIS page for the chosen level
        # (FSD §8), not jump to Overview. Preserve the family across the switch.
        "level_as_href": f"/topic-analysis?level=AS&family={component_family}",
        "level_a_href": f"/topic-analysis?level=A&family={component_family}",
    }


@router.get("/topic-analysis")
def topic_analysis_page(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    student: CurrentStudent,
    level: str | None = None,
    family: str | None = None,
    topic_id: int | None = None,
    topic: str | None = None,
    subtopic_id: int | None = None,
):
    exam_level, component_family, view = _build(
        db, student, level, family, topic_id, topic, subtopic_id
    )
    return templates.TemplateResponse(
        request, "topic-analysis.html", _context(student, exam_level, component_family, view)
    )


@router.get("/topic-analysis/workspace")
def topic_analysis_workspace(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    student: CurrentStudent,
    level: str | None = None,
    family: str | None = None,
    topic_id: int | None = None,
    topic: str | None = None,
    subtopic_id: int | None = None,
):
    """The workspace fragment for an HTMX row-selection swap (§6, §7, FSD §8)."""
    exam_level, component_family, view = _build(
        db, student, level, family, topic_id, topic, subtopic_id
    )
    return templates.TemplateResponse(
        request,
        "partials/topic_analysis_workspace_response.html",
        {
            "view": view,
            "exam_level": exam_level,
            "component_family": component_family,
        },
    )
