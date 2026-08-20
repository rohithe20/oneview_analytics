# Data Model — Design and Rationale

Status: agreed for V1
Scope: Cambridge AS Level Mathematics (9709), single student

This document records *why* the schema looks the way it does. The schema itself
lives in `app/models/` and the migrations in `alembic/`. Read this before
proposing a change to either.

---

## 1. The organising principle

OneView's database is an **OLTP application database**, not a dimensional
warehouse. There are no surrogate-key pipelines, no slowly-changing dimensions,
and no denormalisation for scan performance. Rows are updated in place.

Tables split along one axis:

> **Who writes the row, and does it describe the world or describe the student?**

**Reference tables** describe exam papers as Cambridge published them. Written
once by the seed script, identical for every student, never change after
publication.

**Transactional tables** describe what a student did. Written by the API, one
row per user action, unbounded growth, partitioned by student.

The test that separates them: *if I dropped this table and re-ran the seed
script, would anything real be lost?*

| | Reference | Transactional |
|---|---|---|
| Tables | `subjects`, `topics`, `papers`, `questions`, `sub_parts` | `students`, `attempts`, `sub_part_results` |
| Written by | `python -m app.seed` | API service layer |
| Source of truth | CSVs in `app/seed/data/` (in git) | The database only |
| On loss | Re-run the seed | Gone permanently |
| Growth | Bounded by papers seeded | Grows with use |

This is not a taxonomy for its own sake. It decides five practical things:

1. **Two write paths.** The seed loader fails loudly and aborts on bad data; the
   API returns 422 and keeps serving. Different code, different guarantees.
2. **Backup scope.** Only `attempts` and `sub_part_results` hold irreplaceable
   data. Everything else is reproducible from the repo. This is what makes the
   Backup NFR a small problem rather than a large one.
3. **Test fixtures.** Reference data is seeded once per test session;
   transactional rows are created per test.
4. **Deployment.** Reference data ships with the code. Transactional data must
   survive every deploy.
5. **Multi-student readiness.** Reference data is shared across students;
   transactional data carries `student_id`. Supporting a second student is a
   `WHERE` clause, not a redesign.

---

## 2. Locked decisions

| # | Decision | Rationale |
|---|---|---|
| D1 | Total score is never stored or accepted from the client | A stored total becomes a lie the moment one sub-part mark is corrected |
| D2 | One sub-part maps to exactly one topic | Many-to-many double-counts lost marks; topic figures would stop summing to the paper total |
| D3 | Sub-part labels are flat text (`a`, `b(i)`) | The grain is the mark-bearing part; nesting buys only recursive queries |
| D4 | A paper is subject + component + variant + session + year | 9709/12 and 9709/13 are different papers with different questions |
| D5 | The same paper may be attempted many times | Re-sitting a paper after revision is normal practice |
| D6 | An attempt is `draft` or `completed`; analytics exclude drafts | Partial marks would distort every aggregate |
| D7 | No analytics snapshot table | At this data volume, aggregation is milliseconds; a cache adds only staleness bugs |
| D8 | Every question has at least one `sub_parts` row | Eliminates the "questions with and without sub-parts" branch entirely |

**On D8.** The BRD treats sub-part-less questions as a separate case (§6.3,
BR-01). Honouring that literally would mean two write paths, two validation
rules and two aggregation queries permanently. Instead, a question with no
lettered parts gets one sub-part with an empty label. Every mark in the system
then lives in exactly one place: a `sub_part_results` row. The requirement is
still met — it is met structurally rather than conditionally.

---

## 3. Reference tables

### `subjects` — `id, board, code, name`

`board` and `code` satisfy §6.4's requirement to store examination board and
subject. They also make §17's additional subjects an `INSERT` rather than a
migration, which is what "support future addition of papers without changing the
application design" (§6.4) actually requires.

Surrogate `id` rather than `code` as the key: codes are unique only within a
board, and a varchar key would propagate through every foreign key below.

### `topics` — `id, subject_id, name, parent_id (nullable), sort_order`

A table, not a text column on `sub_parts`. §6.4 requires a consistent taxonomy
so that analytics stay comparable across years — that sentence is a foreign key
written in English. A text column permits `Trigonometry`, `trigonometry` and
`Trig` to coexist and silently fragment every aggregate. BR-04 requires a *valid*
mapping; an FK makes invalid impossible rather than discouraged.

`parent_id` is nullable and unused in V1. §6.4 and §6.5 both mention subtopics.
One nullable column now costs nothing; retrofitting a hierarchy across hundreds
of seeded rows costs a migration and a backfill.

`sort_order` renders topics in syllabus order rather than alphabetically, so the
dashboard reads against the textbook. Supports §6.2's "clear visual status
indicators without overwhelming the student".

V1 values (9709 Paper 1): Quadratics, Functions, Coordinate geometry, Circular
measure, Trigonometry, Series, Differentiation, Integration.

### `papers` — `id, subject_id, component, variant, session, year, total_marks, level`

`component + variant + session + year` is the natural key (D4). A unique
constraint enforces it.

`session` is a three-value enum — `MARCH`, `MAY_JUNE`, `OCT_NOV` — which is
BR-10 made structural. Note that the March series is offered in India only and
as variant 2 only; this is a data reality, not a schema constraint.

**`total_marks` is deliberately stored even though it is derivable.** It is not
a cached aggregate — it is an independently-sourced assertion transcribed from
the printed paper, and its purpose is to detect seed-data errors. If
`SUM(sub_parts.max_marks) != papers.total_marks`, someone mistyped during data
entry. This is a checksum, not a cache. The rule against storing derived values
targets values that can silently *drift* from their inputs; a second source used
to *detect* drift is the opposite case.

`level` (`'AS'` / `'A'`) is a filter convenience for §6.3. Treat it loosely:
Paper 1 counts toward both AS and A Level, so level is not cleanly an attribute
of a paper. For V1, single-subject and single-level, this is adequate.

### `questions` — `id, paper_id, question_number`

Every mark lives on `sub_parts`, so this table exists for three reasons: §6.3
requires question-level totals, the marks-entry screen groups rows by question,
and §17's question-similarity work will need somewhere to hang metadata.

**There is no `max_marks` column.** This is BR-02 enforced structurally — a
question total that disagrees with its parts cannot be represented, because
there is nowhere to store one.

No `sort_order` either: `question_number` is an integer and orders correctly.

### `sub_parts` — `id, question_id, label, max_marks, topic_id, sort_order`

The atomic unit of the whole system. Every mark, every topic attribution and
every analytic resolves to a row here.

`label` is text and may be empty (D8, BR-01). `topic_id` is NOT NULL — BR-04.
`sort_order` is required here, unlike on `questions`, because labels are text
and roman numerals break lexical ordering at `(ix)` against `(x)`.

---

## 4. Transactional tables

### `students` — `id, username, display_name, level, password_hash, created_at`

`password_hash` only, never a password (Security NFR). `id` exists from day one
even though V1 is single-student, per §6.1 and §1.

**Deviation from the BRD:** §6.1 asks the profile to store the student's
subject. That column is omitted. A student studies multiple subjects, so it
becomes a join table the moment §17's multi-subject work begins, and what a
student is studying is already derivable from their attempts. Storing it would
create a second, staler answer to a question the data already answers.

### `attempts` — `id, student_id, paper_id, status, started_at, completed_at, updated_at`

Grain: one row = one occasion of one student sitting one paper.

D5 lives here: **no unique constraint on `(student_id, paper_id)`.**

`status` (`DRAFT` / `COMPLETED`) carries BR-06 and the save-as-draft
requirement.

Both timestamps are load-bearing and do different jobs. Trend charts (§6.2,
§6.6) order by `completed_at`, because a draft left open for two weeks would
misdate itself if ordered by `started_at`. `updated_at` supports §6.3's
edit-a-saved-result requirement.

No `total_score`, no `percentage` (D1).

### `sub_part_results` — `id, attempt_id, sub_part_id, marks_scored`

Grain: one mark.

`UNIQUE (attempt_id, sub_part_id)` makes writes **idempotent** — the same
payload sent twice produces the same state. With HTMX firing a request per
edit, a double-click is a real occurrence, not a theoretical one.

`CHECK (marks_scored >= 0)` at the database. The upper bound
(`marks_scored <= sub_parts.max_marks`, BR-03) spans two tables and so cannot be
a CHECK constraint; it is enforced in the service layer and covered by a test.

No `marks_lost` column: it is `max_marks - marks_scored`, one join away, and
§6.5 needs it aggregated by topic rather than stored per row. Storing it would
require two columns to be updated atomically on every edit, or the analytics
quietly disagree with themselves.

**Row presence is the progress state.** A draft simply has fewer result rows
than its paper has sub-parts, so BR-06's completion check is
`COUNT(results) == COUNT(sub_parts)`. Draft-versus-complete needs no additional
machinery — it falls out of the grain.

---

## 5. Derived values

Nothing derived is stored. Two SQL views carry it:

- **`v_attempt_totals`** — marks scored, marks available, percentage, questions
  attempted, per attempt. Excludes drafts.
- **`v_topic_performance`** — marks scored, marks available, percentage and
  `attempts_count`, per student per topic. Excludes drafts.

`attempts_count` is what powers BR-05. A topic with fewer than three
observations is reported as *insufficient data*, never as a weakness.

---

## 6. Requirement traceability

| Requirement | Mechanism |
|---|---|
| §6.1 unique Student ID | `students.id`, FK on every transactional row |
| §6.3 questions with and without sub-parts | Uniform sub-part grain (D8) |
| §6.3 edit a saved result | `attempts.updated_at`; idempotent result upsert |
| §6.4 board / level / subject / paper / year / session | `subjects` + `papers` columns |
| §6.4 consistent taxonomy | `topics` table + NOT NULL FK |
| §6.5 subtopics | `topics.parent_id`, dormant in V1 |
| §6.5 marks lost by topic | `v_topic_performance` |
| §6.6 burndown | Seeded papers as denominator, completed attempts as numerator |
| BR-01 | `sub_parts.label` may be empty |
| BR-02 | No `max_marks` on `questions` |
| BR-03 | `CHECK (marks_scored >= 0)` + service-layer upper bound |
| BR-04 | `sub_parts.topic_id` NOT NULL |
| BR-05 | `attempts_count` in `v_topic_performance` |
| BR-06 | `attempts.status` + result row count |
| BR-07 preserve history | Reference tables are insert-only; adding a paper cannot alter existing results |
| BR-09 no time taken | Column deliberately absent |
| BR-10 three sessions | `session` enum, three values |
| NFR Scalability | `student_id` on all facts; reference data shared |
| NFR Maintainability | CSV seed + FK taxonomy; new papers require no code change |
| NFR Data Integrity | FKs, unique constraints, checks, seed-time validation |
| NFR Backup | Only two tables hold irreplaceable data |

---

## 7. Known limitations

Accepted for V1, recorded so they are not rediscovered as surprises.

**Cross-subject topic mapping is not constrained.** A paper belongs to a
subject and a topic belongs to a subject, but the FK from `sub_parts.topic_id`
does not know the paper's subject, so a Maths sub-part could in principle
reference a Physics topic. A composite key would close this; it is heavy for a
single-subject V1. Mitigation: the seed loader validates the pairing, and a test
covers it.

**No edit history.** Correcting a mark overwrites the previous value. The BRD
does not require an audit trail. This is a choice, not an oversight.

**Predicted grade has no schema support yet.** It needs a grade-threshold
decision that has not been made. Thresholds move every session, so if real
thresholds are used later they belong in a seeded `grade_thresholds` table keyed
by paper.

**No soft deletes.** Deleting an attempt removes it. Acceptable for a
single-user application; revisit if a parent or teacher view is ever added.
