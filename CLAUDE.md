
# OneView Learning Analytics

Web app for recording Cambridge AS/A Level Mathematics practice-paper
results at sub-part level and surfacing topic weaknesses, predictions,
trends and recommendations.

Solo developer (Rohith, data engineer — strong Python/SQL, learning
frontend). Demo-grade product, production-grade practices. Hard deadline
15 Oct 2026.

## How to work in this repo (agents read this first)

- **Specs are law.** Before building any engine, read the matching file
  in `docs/specs/` AND `docs/qa-matrix.md`. Do not infer behaviour you
  can look up.
- **Tests are the definition of done.** Many engines have a failing test
  suite already written in `tests/`. Your job is to make them pass
  without editing the expected values. If a test seems wrong, STOP and
  flag it — do not change it to force a green run.
- **One task per session.** Implement one service module or one route,
  run its tests, stop. Do not refactor files outside the task.
- **Never edit a committed migration.** Write a new one.
- **Ask before adding a dependency.** The stack below is fixed.
- **If a spec is ambiguous, flag it — do not guess.** The prediction
  worked-example ordering (`test_brd_worked_example`, xfail) is a known
  open item for the PO. Leave such items marked, don't paper over them.

## Stack (fixed)

Python 3.12 · FastAPI · PostgreSQL 16 (Docker, port 5433) ·
SQLAlchemy 2.x + Alembic · Jinja2 + HTMX (no React, no build step) ·
Tailwind via CDN · pytest · ruff · GitHub Actions.

## Architecture (enforced)

- `app/api/routes/` — JSON, HTTP only. Parse, call one service, return.
- `app/web/routes/` — full HTML pages (Jinja).
- `app/web/partials/` — HTML fragments for HTMX swaps.
- `app/services/` — ALL business logic and the engines. Must be testable
  without HTTP. This is where prediction/trend/priority/insight/
  recommendation live.
- `app/models/` — SQLAlchemy ORM only.
- `app/schemas/` — Pydantic contracts.
- `app/seed/` — CSV reference-data loader.

Engines are pure functions over pre-aggregated inputs where possible:
they receive scope-filtered data and return results. They do not query
across scopes. Querying lives in a thin data-access layer that hands the
engine its inputs.

## The scope invariant (non-negotiable — BRD §32)

Every metric is computed within
`(student_id, exam_level, component_family)`.

- The subject is Cambridge Mathematics (9709). "Pure" and "Statistics"
  are FAMILIES of components within that ONE subject, not separate
  subjects. `component_family` is derived from a paper's `component`
  number via a lookup.
- AS and A Level data are NEVER mixed.
- Pure and Statistics are NEVER combined into one score.
- Every read filters on level and component_family. A missing scope
  filter is a bug even if tests pass.

## Data-model decisions (locked — see docs/data-model.md)

- Total scores never stored — summed from sub-parts.
- One sub-part → one topic (FK). Subtopics via `topics.parent_id`.
- Paper = subject + component + variant + session + year.
- Same paper may be attempted many times (no unique student+paper).
- Attempt is `draft` or `completed`; analytics exclude drafts.
- Derived values computed in SQL views / services, never stored.
- New: `study_targets` (student + level + component_family → target
  value). Not keyed by subject — the subject is always Maths; the
  independence is per component family.
- New: a `component → family` mapping (Pure vs Statistics). Keep it as
  seed/config data, e.g. a `component_families` reference table or a
  small config dict, so it's testable and not hard-coded in queries.

## Non-negotiable product rules (BRD §32)

1. UI label is "Predicted Performance", never "Prediction V1".
2. No LLM in any MVP engine — deterministic templates/mappings only.
3. Never hard-code prototype values.
4. Never mix AS/A; never combine subjects.
5. Insufficient data is never evidence of weakness.
6. Priority never ranked solely by marks lost.
7. Correcting a paper never creates a duplicate attempt.
8. Overview and Topic Analysis use the same metrics and rules.
9. Every insight/recommendation records the rule ID that produced it.

## Commands

```bash
docker compose up -d
alembic upgrade head
python -m app.seed
uvicorn app.main:app --reload
pytest                         # all tests
pytest tests/test_priority.py  # one engine
ruff check . && ruff format .
```

## Definition of done for any engine task

- Matching `tests/test_*.py` passes (no expected values altered).
- Scope filter present on every read.
- Rule IDs recorded where the spec requires traceability.
- ruff clean.
- One commit on a feature branch, PR into main.
