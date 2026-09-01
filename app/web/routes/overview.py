from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models import Student

router = APIRouter()
templates = Jinja2Templates(directory="app/web/templates")

STUDENT_ID = 1


def student_initials(display_name: str) -> str:
    parts = display_name.split()
    return "".join(p[0] for p in parts[:2]).upper()


@router.get("/overview")
def overview(request: Request, db: Annotated[Session, Depends(get_db)]):
    student = db.scalar(select(Student).where(Student.id == STUDENT_ID))
    student_name = student.display_name if student else "Unknown Student"
    exam_level = student.level if student else "AS"

    return templates.TemplateResponse(
        request,
        "overview.html",
        {
            "active_nav": "overview",
            "student_name": student_name,
            "student_initials": student_initials(student_name),
            "exam_level": exam_level,
        },
    )
