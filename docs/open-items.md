# Open Items

Running log of specced-but-unresolved gaps and ambiguities flagged
during implementation, per CLAUDE.md's "if a spec is ambiguous, flag it
— do not guess." Each entry stays here until the PO resolves it; do not
delete or silently work around an entry without updating this file.

---

## Prediction — worked-example ordering

- **Status:** open, needs PO decision
- **Where:** `docs/specs/prediction-v1.md` §"most recent"; test
  `test_brd_worked_example` in `tests/test_prediction.py` (marked
  `xfail`)
- **Issue:** the BRD worked example is ambiguous about which attempt
  counts as "most recent" when computing the weighted prediction. Two
  readings give different expected values (the xfail test currently
  expects one of them, unconfirmed).
- **Action needed:** PO confirms the intended ordering; then un-xfail
  the test with the confirmed value.

## Insight/Recommendation — no approved text for "sufficient data, no issue qualifies"

- **Status:** open, needs PO decision
- **Where:** `app/services/insight.py` (`NO_INSIGHT_RULE_ID = "INS-00"`),
  `app/services/recommendation.py` (`NO_RECOMMENDATION_RULE_ID =
  "REC-00"`); rendered in `app/web/templates/partials/family_panel.html`
- **Issue:** BRD §21/§24's approved template lists cover every
  weakness case and the insufficient-data case, but not "sufficient
  data, nothing qualifies as a priority." Rule 6 of the insight spec
  (§23) falls through to this state with no matching template, and the
  recommendation engine mirrors it with `REC-04` (Inconsistent) also
  left unreachable since no engine computes an "inconsistent" signal.
- **Current behaviour:** `select_insight`/`select_recommendation`
  return `rule_id` set but `text=None`. The Overview page omits the
  Insight and Recommendation cards entirely in this case rather than
  showing invented copy.
- **Action needed:** PO supplies approved copy for the no-issue state
  (and confirms whether `REC-04`/an "inconsistent" signal is in scope
  for MVP at all), or confirms that omitting the cards is the intended
  UI behaviour.

## Overview UI — Predicted Performance mark-range display

- **Status:** open, needs PO/spec decision
- **Where:** `docs/specs/overview-ui.md` §4.1 (mockup shows "78%" with
  "≈ 58–60 / 75" as secondary text); `app/services/overview.py`
  `FamilyOverview.predicted_percentage`
- **Issue:** the UI spec's mockup shows a secondary mark-range under
  the predicted percentage, but `FamilyOverview` (per
  `overview-assembly.md`) carries no total-marks or predicted-range
  field, and the prediction engine returns a percentage only.
- **Current behaviour:** the Predicted Performance card shows the
  percentage only; no range is rendered or fabricated.
- **Action needed:** decide whether the assembly layer should compute
  a predicted mark range (needs a total-marks source per component
  family) or whether the mockup's range display is dropped for MVP.

## Seed data — no Statistics-family topics

- **Status:** open, needs seed-data work
- **Where:** `app/seed/data/topics.csv`, `app/seed/data/papers.csv`,
  `app/seed/data/questions.csv`
- **Issue:** the seeded reference data only covers one Pure paper
  (`9709_11_MJ_2025`) and Pure-family topics (Quadratics, Functions,
  Coordinate Geometry, Circular Measure, Trigonometry, Series,
  Differentiation, Integration). No Statistics component (5/6) paper,
  questions, or Statistics-specific topics (e.g. Probability, Discrete
  Random Variables) exist in the seed CSVs.
- **Current behaviour:** `tests/test_overview_assembly.py`'s
  scope-isolation fixture, and the local demo seed used to verify the
  Overview page, both construct a synthetic Statistics paper that
  reuses an existing *Pure* topic FK purely to satisfy the not-null
  constraint — it does not represent a real Statistics topic.
- **Action needed:** seed real Statistics papers/questions/topics
  before the Statistics column can show meaningful priority-area data
  in a demo or in production.

## Overview page — student_id=1 not present in dev DB

- **Status:** informational, no code change needed
- **Where:** `app/web/routes/overview.py` `STUDENT_ID = 1` (per
  `docs/specs/overview-ui.md` §8: "hardcode student_id=1 for now")
- **Issue:** the local dev Postgres DB's only pre-existing student was
  seeded at id=3 (`demo_student` / "Laya Eshwarwak"), not id=1. Built
  as specced, the Overview page would show the empty state for a
  student that doesn't exist.
- **Current behaviour:** a second student was seeded locally at id=1
  (`demo_student_1` / "Alex Carter", AS level) with 6 Pure attempts
  (populated/Improving-trend state) and 2 synthetic Statistics attempts
  (insufficient-data state), purely to verify the UI. The seed script
  is a one-off in the scratch directory, not committed to the repo or
  `app/seed/`.
- **Action needed:** none for MVP — once real auth exists, `STUDENT_ID`
  goes away. Worth confirming with the PO whether id=1 should be
  reserved for a canonical demo account before the Oct 2026 demo.
