# OneView Learning Analytics

Web app for recording Cambridge AS Level Mathematics (9709) past-paper results
at sub-part level and surfacing topic-level weaknesses.

Solo developer. Demo-grade product, production-grade practices.

## Who I am

Data engineer. Strong Python and SQL. Limited JavaScript, HTML and CSS.
Explain frontend concepts; you can assume I know backend and database ones.

**Always explain the reasoning behind a design choice, not just the code.** If
there is a simpler option you rejected, say what it was and why.

## Stack

- Python 3.12, FastAPI
- PostgreSQL 16 (Docker, port 5433)
- SQLAlchemy 2.x ORM, Alembic migrations
- Jinja2 templates + HTMX for the frontend (no React, no build step)
- Tailwind via CDN
- pytest, ruff
- GitHub Actions CI

Do not introduce a new dependency without asking first.

## Architecture rules

- `app/api/routes/` — HTTP only. Parse request, call one service, return.
  No business logic here.
- `app/services/` — all business rules live here. Must be testable without HTTP.
- `app/models/` — SQLAlchemy ORM classes only.
- `app/schemas/` — Pydantic request/response models.
- `app/seed/` — CSV loader for reference data.

## Data model decisions (locked — do not propose alternatives)

Full rationale in `docs/data-model.md`. Read it before proposing any schema
change.

- Grain: one row in `sub_part_results` = one sub-part, one attempt, one student.
- Total scores are **never** stored or accepted from the client. Always summed
  from sub-parts.
- Every question has at least one `sub_parts` row. A question with no lettered
  parts gets one sub-part with an empty label. There is no special case for
  "questions without sub-parts".
- One sub-part maps to exactly one topic. Foreign key, not a join table.
- Sub-part labels are flat text (`a`, `b(i)`, `c(ii)`). No parent/child nesting.
- A paper is uniquely identified by subject + component + variant + session +
  year. The variant digit matters: 9709/12 and 9709/13 are different papers.
- The same paper may be attempted many times. No unique constraint on
  (student_id, paper_id).
- An attempt is `draft` or `completed`. Drafts may have partial results.
  Analytics exclude drafts.
- Derived values (`marks_lost`, `percentage`, totals) are computed in SQL views,
  never stored. There is no analytics snapshot table.

## Business rules

- Reject `marks_scored` above the sub-part's `max_marks`, or below zero.
- An attempt cannot be completed until every sub-part on the paper has a result.
- A topic with fewer than 3 observations is reported as *insufficient data*,
  never as a weakness.
- The predicted grade is an estimate, labelled as such, never presented as an
  official prediction.

## Working preferences

- One task per session. Small, reviewable diffs.
- Write the test alongside the code, in the same change.
- Never run `alembic revision --autogenerate` and apply it in one step — show me
  the generated migration first.
- Never modify a migration that has already been committed. Write a new one.
- Don't refactor files I didn't ask you to touch.
- If a request is ambiguous, ask one question rather than guessing.

## Commands

```bash
docker compose up -d          # start Postgres
alembic upgrade head          # apply migrations
python -m app.seed            # load reference data
uvicorn app.main:app --reload # run the API
pytest                        # tests
ruff check . && ruff format . # lint
```
