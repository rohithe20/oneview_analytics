# Priority Engine — Top 3 Priority Areas

Source: BRD §9, §19, §20. **This is the most complex engine. Read it
twice.** Statuses: **High**, **Medium**, **Monitor**, plus "no priority".

## What it does

For each subtopic in scope, classifies how urgently it needs attention,
then ranks the qualifying subtopics and returns the top 3 per subject.

## Two-stage process

Stage 1: classify EACH subtopic into a priority level (or none).
Stage 2: rank the classified subtopics and take the top 3.

## Inputs per subtopic

- `subtopic_avg`: the student's average % on this subtopic, in scope.
- `family_avg`: the student's overall average % across the subject, in
  scope.
- `gap = family_avg − subtopic_avg` (positive means below average).
- `observation_count`: number of relevant observations for this subtopic.
- `repeated_error_signal`: boolean, defined below.
- `improving`: whether this subtopic's recent direction is upward.

## Repeated-error signal (§19 footnote)

`repeated_error_signal = True` when the subtopic has an error in **at
least 50% of the student's last 4 relevant attempts**, provided at least
3 relevant attempts exist. Below 3 relevant attempts, the signal is
always False (insufficient data).

## Stage 1 — classification rules (§19, apply top to bottom, first match wins)

| # | Condition | Priority |
|---|---|---|
| 1 | observation_count < 3 | **No priority** — "More data needed", never "weak" |
| 2 | gap ≥ 15 | **High** |
| 3 | gap ≥ 10 AND repeated_error_signal | **High** |
| 4 | 5 ≤ gap ≤ 14 (with sufficient data) | **Medium** |
| 5 | 0 ≤ gap ≤ 4, OR (improving but slightly below benchmark) | **Monitor** |
| 6 | at/above subject avg, stable/improving, no repeated-error signal | **No priority** — not displayed |

Note rule 1 gates everything: sufficiency is checked before any weakness
classification. Note rule 3 lets a 10–14pp gap escalate to High *only*
when repeated errors are present; without the signal a 10–14pp gap is
Medium (rule 4).

## Stage 2 — ranking and tie-breaks (§20, in order)

1. Rank High above Medium above Monitor.
2. Within the same priority: **largest gap** first.
3. Still tied: **higher recent error frequency** first.
4. Still tied: **more relevant observations** first.
5. Take the top 3. If fewer than 3 qualify, return only those.

## Function contract

    rank_priorities(subtopics: list[SubtopicStats]) -> list[PriorityArea]

- `subtopics`: pre-aggregated stats per subtopic, already scope-filtered.
  The engine does not query — it classifies and ranks.
- Returns up to 3 `PriorityArea` objects, each with topic, subtopic,
  percentage, priority label, and the gap (for the drill-down link).

## Marks-lost rule (§9, §32)

Marks lost MAY inform analysis but MUST NOT be the primary ranking key.
Rank by the gap-below-average rules above, not by marks lost. This is a
non-negotiable BRD rule.

## Test cases (from QA matrix — see tests/test_priority.py)

- OV-T-012: gap 16pp, ≥3 obs → High.
- OV-T-013: gap 10pp + repeated errors ≥50% → High.
- OV-T-014: gap 10pp, no repeated errors → Medium.
- OV-T-015: < 3 observations → no weak classification, more-data state.
- OV-T-016: tie between priorities → tie-breaks applied in documented
  order.

## What NOT to do

- Do not rank by marks lost.
- Do not classify a subtopic with < 3 observations as weak.
- Do not return more than 3.
- Do not read across levels or subjects.
- Do not let a 10–14pp gap become High without the repeated-error signal.
