# Subtopic Data — seed structure

The Overview snapshot shows priority at TOPIC + SUBTOPIC granularity
(e.g. "Functions / Inverse Functions"). The schema supports this
(`topics.parent_id`) but the seed data has no subtopics. This spec adds
them.

## Model — already exists, confirm it

`topics` already has:
- `id`, `subject_id`, `name`, `parent_id` (nullable FK to topics.id),
  `sort_order`

A TOPIC is a row with `parent_id IS NULL`.
A SUBTOPIC is a row with `parent_id` = its topic's id.

No migration needed — this is data, not schema.

## Seed CSV change

Add a `subtopics.csv` (or extend `topics.csv` with a parent column).
Recommended: one file, a `parent_topic` column that is blank for
top-level topics and names the parent for subtopics.

    app/seed/data/topics.csv
    subject_code,name,parent_topic,sort_order
    9709,Functions,,2
    9709,Inverse Functions,Functions,1
    9709,Composite Functions,Functions,2
    9709,Quadratics,,1
    9709,Discriminants,Quadratics,1
    ...

The loader resolves `parent_topic` to `parent_id` by name lookup within
the subject (same pattern as the existing topic_name → topic_id
resolution). Blank parent_topic → parent_id NULL (a top-level topic).

## Which subtopics?

For the Pure family (demo scope), add a few real subtopics under each of
the 8 Pure topics. They must be real Cambridge 9709 subtopics — do not
invent. Examples (CONFIRM against the syllabus):
- Functions → Inverse Functions, Composite Functions, Domain & Range
- Quadratics → Discriminants, Completing the Square
- Trigonometry → Identities, Equations, Graphs
- Differentiation → Chain Rule, Stationary Points
- Integration → Definite Integrals, Area Under Curve

For the demo, subtopics under Integration (the deliberate weak topic)
matter most — they give the priority engine specific subtopics to
surface.

## Sub-part mapping consequence

`sub_parts.topic_id` currently points at a TOPIC. For subtopic-level
priority, sub-parts should point at a SUBTOPIC where one applies, and the
topic is derived via the subtopic's parent.

Decision for MVP: point `sub_parts.topic_id` at the most specific level
available — a subtopic if the question maps to one, else the topic. The
priority engine's `SubtopicStats` already carries both `topic` and
`subtopic`; the assembly layer derives topic from the subtopic's parent.

This means the questions.csv `topic_name` column may now name a subtopic.
The loader must resolve it against all topics (parent or child) within
the subject.

## Demo-data consequence

`app/seed/demo_attempts.py`'s WEAK_TOPIC_NAME should point at a subtopic
under Integration (e.g. "Definite Integrals") so the priority row shows
"Integration / Definite Integrals" like the snapshot, not
"Integration / Integration".

## Validation

- Every subtopic's `parent_topic` must resolve to an existing top-level
  topic in the same subject — fail loudly on an unknown parent.
- A subtopic's parent must itself have parent_id NULL (one level only —
  no sub-subtopics for MVP).

## What NOT to do

- Do not invent non-syllabus subtopics.
- Do not create more than one level of nesting.
- Do not change the topics table schema — parent_id already exists.
