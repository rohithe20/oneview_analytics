# Mark-Scale Source — percentages to marks

The snapshot shows marks everywhere: "58.4 / 75", "64 - 68 / 75",
"Average Score 58.4 / 75 (77.9%)". The engines currently return
PERCENTAGES only. This spec adds the total-marks source so the assembly
layer can present marks alongside percentages.

## The core question: what is the "/ 75"?

It is the total marks of a full paper in that component family. For the
Pure family it is 75 (MVP fixed total). For Statistics the snapshot
shows "/ 60". So the denominator is PER COMPONENT FAMILY.

## Where the total comes from

The papers table already has `total_marks` per paper. Within a family,
papers share the same total for MVP (all Pure papers = 75). So:

    family_total_marks(family) = the total_marks of papers in that family
                                 (assert they agree; use the value)

Add a helper in the data-access / assembly layer:

    def get_family_total_marks(db, exam_level, component_family) -> int:
        # returns the total_marks shared by papers in this scope
        # (for MVP they are uniform; if they differ, use the most common
        #  or flag it)

Do NOT hard-code 75. Read it from the papers in scope. The snapshot's
Statistics "/ 60" proves the denominator varies by family.

## What the assembly layer computes

Extend `FamilyOverview` (overview-assembly.md) with mark-scale fields
derived from the existing percentages × family_total_marks:

    total_marks: int                  # e.g. 75 for Pure

    # Average score as a mark
    average_score_marks: float | None   # average_percentage/100 * total
    # Recent score as a mark
    recent_score_marks: float | None

    # Predicted performance as a mark RANGE (snapshot: "64 - 68 / 75")
    predicted_marks_low: float | None
    predicted_marks_high: float | None

## The predicted range (snapshot: "64 - 68 / 75", "85% - 91%")

The prediction engine returns a single percentage. The snapshot shows a
RANGE. For MVP, derive a small band around the predicted percentage:

    band = a fixed +/- margin (e.g. +/- 3 percentage points) OR
           the confidence interval if the engine exposes one.

Decision needed (flag if unspecified): the BRD does not define the range
width. Use +/- 3pp as a documented default and note it in Open Items for
PO confirmation. Convert both ends to marks against total_marks.

    predicted_marks_low  = (predicted_pct - 3)/100 * total_marks
    predicted_marks_high = (predicted_pct + 3)/100 * total_marks

Clamp to [0, total_marks]. Show the percentage range too ("85% - 91%").

## Rounding / display

- Marks shown to 1 decimal where the snapshot does (58.4), else nearest.
- Percentage secondary in parentheses or sub-text per overview-ui.md.
- Never show a mark without its scale ("/ 75").

## Test contract

- A scope averaging 77.9% with total 75 → average_score_marks ≈ 58.4.
- Predicted 88% with total 75, +/-3pp → range ≈ 63.8 - 68.3 / 75.
- A family with total 60 (if seeded) uses 60, not 75 — proves it is not
  hard-coded.

## Open Items to log

- Predicted-range WIDTH is not specified by the BRD. Using +/-3pp as a
  documented default; PO to confirm.
  (This supersedes the earlier "mark-range display" open item, which is
  now resolved to "build it" — only the width needs confirming.)

## What NOT to do

- Do not hard-code 75.
- Do not fabricate a total when no papers are seeded in scope — return
  None and let the card show its insufficient/empty state.
- Do not change the prediction engine — the range is derived in the
  assembly layer, not in the engine.
