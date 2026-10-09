from __future__ import annotations

import random
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select, text

from app.core.db import SessionLocal
from app.models import Attempt, Paper, Student, SubPart, SubPartResult, Topic
from app.models.enums import AttemptStatus

# The demo login accounts, main account first. Overview renders whichever
# student is logged in (docs/specs/login-auth.md), so an account with no
# attempts shows the empty state no matter how good the seed data is — every
# account someone actually signs in as needs its own copy. Each gets the
# IDENTICAL run of marks (see RANDOM_SEED), so which one you demo from
# changes nothing on screen but the name.
#
# Rows are matched by username and created only if missing; an existing
# password_hash is never touched. Give a new account a real one with
# `python -m app.seed.set_password <username> <password>` — until then its
# placeholder hash fails login cleanly. This module is the only committed
# source of these students' attempts — see docs/open-items.md.
DEMO_STUDENTS: list[tuple[str, str]] = [
    ("demo_student", "Laya Eshwarwak"),
    ("demo_student_1", "Alex Carter"),
]
DEMO_MARKER_PREFIX = "[DEMO]"  # stored in attempt notes for identification

# A subtopic name the demo student is deliberately weak at, so priority
# and insight have a clear story. Must be a real subtopic name from the
# seed (topics.csv) — a child of Integration — and, per the rule below,
# one that questions.csv maps in at least MIN_WEAK_TOPIC_PAPERS distinct
# papers. "Definite & indefinite integration" appears in only one paper,
# so it cannot clear the priority engine's observation gate now that
# re-attempting a paper adds no observation.
#
# Exported (with MIN_WEAK_TOPIC_PAPERS) for tests/test_seed.py, which
# guards the Pure weakness against a questions.csv edit that silently
# drops it below the gate. It is the Pure plan's weak topic; Statistics
# carries its own (see DEMO_PLANS).
WEAK_TOPIC_NAME = "Integration as reverse of differentiation"

# Statistics' deliberate weak subtopic — a child of Probability, mapped in
# enough recent papers to clear the observation gate within the demo subset.
# Distinct from the Pure weakness so each family tells its own story.
STATS_WEAK_TOPIC_NAME = "Conditional probability"

# Every metric counts the most recent attempt at each DISTINCT paper
# (planning-performance.md, PO decision 2026-09-05), so the demo needs enough
# distinct papers for Papers Completed — and for the >=5 sufficient-data gate,
# the trend engine's 4 and the prediction engine's 5 — to have anything to show.
MIN_DISTINCT_PAPERS = 5

# priority.py gates a subtopic at MIN_OBSERVATIONS=3 observations before it can
# be ranked, and an observation is now a distinct paper: re-attempting one paper
# three times is still a single observation. So the weak area has to be carried
# by at least three different papers, which is asserted before seeding rather
# than assumed — a questions.csv edit that drops below it must fail loudly, not
# quietly empty the Priority Areas card.
MIN_WEAK_TOPIC_PAPERS = 3

# Statistics has 23 seeded papers across 2023-2025, far more than a real
# student would sit before a demo. The login student attempts a realistic
# recent slice instead of the whole back-catalogue: the most recent
# STATS_MAX_PAPERS papers sat no earlier than STATS_RECENT_YEAR_MIN. This
# keeps the Statistics story plausible while still clearing MIN_DISTINCT_PAPERS
# and the weak-area gate. Pure keeps its whole (smaller) scope — see DEMO_PLANS.
STATS_RECENT_YEAR_MIN = 2024
STATS_MAX_PAPERS = 9

# The weakness must read as a real weak area, not as broken data: low but
# clearly nonzero. These bound the weak subtopic's ability across the run
# (it improves with the rest), keeping the aggregate percentage in the
# 30-45% band rather than bottoming out at 0.
WEAK_ABILITY_START = 0.32
WEAK_ABILITY_END = 0.44
WEAK_NOISE = 0.05  # tighter than general noise so the band holds
# Per-sub-part noise. Kept well below the ability step between consecutive
# papers so the improving signal survives averaging: the trend engine compares
# the last two attempts against the previous two, and at ~12 sub-parts a paper
# a 0.12 sigma leaves ~3.5pp of noise per attempt — enough to swamp the ramp
# and land the demo on "Stable".
GENERAL_NOISE = 0.06

# The overall ability ramp across the run. Spread end-to-end rather than
# per-attempt so the improvement stays gentle however many papers are
# seeded, while still clearing the trend engine's 5.0pp IMPROVING_THRESHOLD.
BASE_ABILITY_START = 0.55
BASE_ABILITY_END = 0.87

# Reproducible demo data. Re-seeded at the start of every family's run
# rather than once at import, which is what makes each demo account's marks
# identical instead of each one continuing the previous student's stream.
RANDOM_SEED = 42


@dataclass(frozen=True)
class FamilyPlan:
    """One family's worth of synthetic attempts for a demo student.

    A plan is pure configuration: it names the scope (BRD §32), the weak
    subtopic to sink, and the ability ramp. The seeder below reads only its
    own plan's scope — it must not reach across levels or families any more
    than the analytics layer does.

    recent_year_min / max_papers trim the full in-scope set to a realistic
    recent slice. Left as None (Pure), the student attempts every paper in
    scope; set (Statistics), the student attempts only the most recent
    max_papers papers sat in or after recent_year_min.
    """

    exam_level: str
    component_family: str
    weak_topic_name: str
    weak_ability_start: float = WEAK_ABILITY_START
    weak_ability_end: float = WEAK_ABILITY_END
    base_ability_start: float = BASE_ABILITY_START
    base_ability_end: float = BASE_ABILITY_END
    min_distinct_papers: int = MIN_DISTINCT_PAPERS
    min_weak_topic_papers: int = MIN_WEAK_TOPIC_PAPERS
    recent_year_min: int | None = None
    max_papers: int | None = None


# Both families the login student demos, so Overview and Topic Analysis have
# a full, populated story on each side (all six components: prediction,
# metrics, trend, priority, insight, recommendation). AS/A are never mixed and
# Pure/Statistics never combined (BRD §32) — each plan is its own scope.
DEMO_PLANS: list[FamilyPlan] = [
    FamilyPlan(
        exam_level="AS",
        component_family="Pure",
        weak_topic_name=WEAK_TOPIC_NAME,
    ),
    FamilyPlan(
        exam_level="AS",
        component_family="Statistics",
        weak_topic_name=STATS_WEAK_TOPIC_NAME,
        recent_year_min=STATS_RECENT_YEAR_MIN,
        max_papers=STATS_MAX_PAPERS,
    ),
]


def get_or_create_demo_student(db, username: str, display_name: str) -> Student:
    """Find the demo student by username, creating it only if absent.

    Never overwrites an existing row: the account may already carry a real
    bcrypt hash set with `python -m app.seed.set_password`, and re-running the
    seeder must not lock anyone out of it.
    """
    student = db.scalar(select(Student).where(Student.username == username))
    if student is None:
        student = Student(
            username=username,
            display_name=display_name,
            level="AS",
            password_hash="not-a-real-hash",
        )
        db.add(student)
        db.flush()
    return student


def wipe_demo_attempts(db, student: Student) -> int:
    attempts = db.scalars(select(Attempt).where(Attempt.student_id == student.id)).all()
    n = 0
    for a in attempts:
        if (a.notes or "").startswith(DEMO_MARKER_PREFIX):
            db.delete(a)  # cascade removes sub_part_results
            n += 1
    return n


def score_for_subpart(
    sub_part: SubPart,
    topic_name: str,
    base_ability: float,
    weak_ability: float,
    weak_topic_name: str,
) -> int:
    """Return marks_scored for one sub-part.

    base_ability is the student's rough proficiency (0-1). The weak
    subtopic is scored against weak_ability instead, so it surfaces as a
    priority while staying well clear of zero.
    """
    if topic_name == weak_topic_name:
        ability, noise = weak_ability, WEAK_NOISE
    else:
        ability, noise = base_ability, GENERAL_NOISE
    # add a little noise, clamp to [0, max_marks]
    frac = min(1.0, max(0.0, random.gauss(ability, noise)))
    return round(frac * sub_part.max_marks)


# Chronological order within a year, so the improving trend runs forward in
# exam time as well as in completed_at. The ExamSession enum is declared in
# calendar order but stored by value, so rank it explicitly.
SESSION_ORDER = {"MARCH": 0, "MAY_JUNE": 1, "OCT_NOV": 2}


def papers_in_scope(
    db,
    exam_level: str,
    component_family: str,
    *,
    recent_year_min: int | None = None,
    max_papers: int | None = None,
) -> list[Paper]:
    """Papers for one (level, family) scope, oldest sitting first.

    The family lookup goes through component_families — the same reference
    table planning.get_available_papers uses — never a hard-coded component
    list (CLAUDE.md, data-model.md).

    recent_year_min drops anything sat before that year; max_papers then keeps
    only the most recent that many (still oldest-first, so the ramp runs
    forward through them). Both default to None, which returns the whole scope.
    """
    components = [
        row[0]
        for row in db.execute(
            text("SELECT component FROM component_families WHERE family = :family"),
            {"family": component_family},
        ).all()
    ]
    if not components:
        raise SystemExit(
            f"No components mapped to family '{component_family}'. Run `alembic upgrade head`."
        )

    papers = db.scalars(
        select(Paper).where(Paper.level == exam_level, Paper.component.in_(components))
    ).all()
    papers = sorted(
        papers, key=lambda p: (p.year, SESSION_ORDER.get(p.session.name, 99), p.variant)
    )

    if recent_year_min is not None:
        papers = [p for p in papers if p.year >= recent_year_min]
    if max_papers is not None and len(papers) > max_papers:
        # Keep the most recent max_papers; the slice preserves oldest-first order.
        papers = papers[-max_papers:]
    return papers


def seed_demo_attempts(db, student: Student, plan: FamilyPlan) -> tuple[int, int]:
    """Exactly one completed attempt per DISTINCT paper in the plan, improving.

    One attempt per paper is now the only shape worth seeding: every metric
    reduces a paper's attempts to the most recent one, so a re-sit would add
    nothing to Papers Completed, the averages, the trend series, the
    prediction inputs or a subtopic's observation count. The weak area gets
    its evidence from being carried by several different papers instead.

    Returns (attempts_created, distinct_papers_attempted) — equal by
    construction, returned as a pair because the caller reports both and the
    equality is the property worth showing.
    """
    # Every family gets the same run of marks, not a continuation of the
    # previous family's or account's random stream.
    random.seed(RANDOM_SEED)

    papers = papers_in_scope(
        db,
        plan.exam_level,
        plan.component_family,
        recent_year_min=plan.recent_year_min,
        max_papers=plan.max_papers,
    )
    if not papers:
        raise SystemExit(
            f"No {plan.exam_level} {plan.component_family} papers seeded. "
            f"Run `python -m app.seed` first."
        )
    if len(papers) < plan.min_distinct_papers:
        raise SystemExit(
            f"Only {len(papers)} distinct {plan.exam_level} {plan.component_family} "
            f"paper(s) in the demo slice; the demo needs at least "
            f"{plan.min_distinct_papers}. Add rows to app/seed/data/papers.csv "
            f"(and matching questions.csv rows), or widen the plan's recent slice."
        )

    weak_papers = [p for p in papers if _carries_weak_subtopic(db, p, plan.weak_topic_name)]
    if len(weak_papers) < plan.min_weak_topic_papers:
        raise SystemExit(
            f"'{plan.weak_topic_name}' is mapped in only {len(weak_papers)} distinct "
            f"{plan.exam_level} {plan.component_family} paper(s) in the demo slice; the "
            f"demo needs at least {plan.min_weak_topic_papers} so it clears the priority "
            f"engine's observation gate. Point the plan's weak topic at a subtopic "
            f"app/seed/data/questions.csv maps more widely, or add rows there."
        )

    # Simulate improvement over time: ability rises monotonically across the
    # run, so the start/end gap clears the trend engine's 5.0pp
    # IMPROVING_THRESHOLD and the demo reads as Improving.
    start = datetime(2026, 2, 1)
    last = len(papers) - 1
    for index, paper in enumerate(papers):
        _record_attempt(db, student, paper, index, index / max(1, last), start, plan)

    return len(papers), len(papers)


def _carries_weak_subtopic(db, paper: Paper, weak_topic_name: str) -> bool:
    """True when this paper has at least one sub-part on weak_topic_name."""
    return (
        db.scalar(
            select(SubPart.id)
            .join(SubPart.question)
            .join(SubPart.topic)
            .where(SubPart.question.has(paper_id=paper.id))
            .where(Topic.name == weak_topic_name)
            .limit(1)
        )
        is not None
    )


def _record_attempt(
    db,
    student: Student,
    paper: Paper,
    index: int,
    progress: float,
    start: datetime,
    plan: FamilyPlan,
) -> None:
    """One completed, marked-up synthetic attempt at `progress` along the ramp."""
    base_ability = (
        plan.base_ability_start + (plan.base_ability_end - plan.base_ability_start) * progress
    )
    # The weak subtopic improves too, across the plan's weak band.
    weak_ability = (
        plan.weak_ability_start + (plan.weak_ability_end - plan.weak_ability_start) * progress
    )

    attempt = Attempt(
        student_id=student.id,
        paper_id=paper.id,
        status=AttemptStatus.COMPLETED,
        notes=f"{DEMO_MARKER_PREFIX} synthetic attempt {index + 1}",
        completed_at=start + timedelta(days=7 * index),
    )
    db.add(attempt)
    db.flush()

    # Load every sub-part of the paper and score it.
    sub_parts = db.scalars(
        select(SubPart).join(SubPart.question).where(SubPart.question.has(paper_id=paper.id))
    ).all()

    for sp in sub_parts:
        topic_name = sp.topic.name if sp.topic else ""
        marks = score_for_subpart(sp, topic_name, base_ability, weak_ability, plan.weak_topic_name)
        db.add(
            SubPartResult(
                attempt_id=attempt.id,
                sub_part_id=sp.id,
                marks_scored=marks,
            )
        )


def main() -> int:
    wipe_only = "--wipe" in sys.argv
    with SessionLocal() as db:
        for username, display_name in DEMO_STUDENTS:
            student = get_or_create_demo_student(db, username, display_name)
            removed = wipe_demo_attempts(db, student)

            if wipe_only:
                print(f"Removed {removed} demo attempt(s) for '{username}' (id={student.id}).")
                continue

            # One wipe covers the student's whole demo history; seed each
            # family's plan in turn. The families are separate scopes and
            # never mix (BRD §32).
            print(f"Removed {removed} old demo attempt(s) for '{username}' (id={student.id}).")
            for plan in DEMO_PLANS:
                created, distinct_papers = seed_demo_attempts(db, student, plan)
                print(
                    f"  {plan.exam_level} / {plan.component_family}: created {created} "
                    f"attempt(s) across {distinct_papers} distinct paper(s); "
                    f"weak topic '{plan.weak_topic_name}'."
                )

        # One transaction for every account: a failure part-way through leaves
        # no student holding a half-seeded run.
        db.commit()
        return 0


if __name__ == "__main__":
    sys.exit(main())
