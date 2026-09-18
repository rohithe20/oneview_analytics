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
- **Issue:** the seeded reference data covers nine AS Pure papers and
  Pure-family topics only (Quadratics, Functions,
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

## Planning — what "Papers Completed" counts

- **Status:** resolved — PO decision 2026-09-05, implemented
- **Where:** `docs/specs/planning-performance.md` §"The counted attempt";
  `app/services/overview.py`; migration `7f3c9d2b41ae`
- **Issue:** `Papers Completed` counted ATTEMPTS, not distinct papers, so
  6 attempts on 1 paper read "6 completed" against a target measured in
  *papers* — and completion could exceed 100%. A first pass fixed the
  count alone, which left the rest of the panel inconsistent with it: the
  averages, trend, prediction and priority observation counts still
  treated a re-sit as a second observation.
- **PO decision:** for each distinct paper, only the MOST RECENT attempt
  counts — for every metric and every engine, not just the count. A paper
  attempted twice contributes one value.
- **Current behaviour:** implemented once in the data-access layer. The
  `v_latest_paper_attempts` view names the attempt that counts;
  `v_topic_performance` is built on it and `app/services/overview.py`
  joins it, so the engines inherit the reduction. `attempts_count` and
  `papers_completed` are now the same number, and the `>=5` sufficiency
  gate counts distinct papers.
- **Action needed:** none.

## Planning — the target ceiling is 1 with current seed data

- **Status:** resolved — `papers.csv` now seeds nine AS Pure papers
- **Where:** `app/services/planning.py` `set_target` /
  `get_available_papers`; `app/seed/data/papers.csv`
- **Issue:** OV-PL-003 caps a practice target at Available Papers, and
  `papers.csv` seeded exactly one paper, so the only targets that
  validated were 0 and 1 for AS/Pure and 0 for every other scope.
- **Current behaviour:** nine AS Pure papers are seeded, so the AS/Pure
  ceiling is 9. The Edit Target form's `max` follows the live count, and
  the form is still disabled with an explanatory note where that count is
  0 (AS/Statistics, both A Level scopes — see the Statistics seed item
  above, still open).
- **Action needed:** none for Pure; the Statistics scopes stay blocked on
  the Statistics seed-data item above.

## Overview page — which student the demo data belongs to

- **Status:** resolved — `demo_attempts.py` owns both demo accounts
- **Where:** `app/seed/demo_attempts.py` `DEMO_STUDENTS`
- **Issue:** the page used to hardcode `student_id = 1`, while the local
  dev DB's only pre-existing student was id=3 (`demo_student` / "Laya
  Eshwarwak"). Built as specced (`docs/specs/overview-ui.md` §8,
  "hardcode student_id=1 for now"), the Overview would show the empty
  state for a student that didn't exist.
- **Former behaviour:** a second student was seeded locally at id=1
  (`demo_student_1` / "Alex Carter") by a one-off script in the scratch
  directory, never committed. That script hard-coded `marks_scored = 0`
  for every Integration sub-part, which is why the priority area read
  0.0%, and it invented a component-5 Statistics paper absent from
  `papers.csv`. The scratch attempts and the phantom Statistics paper
  were deleted.
- **Current behaviour:** the hardcode is gone — `student_id` comes from
  the session (`docs/specs/login-auth.md`), so the page belongs to
  whoever logs in. `demo_attempts.py` therefore seeds EVERY demo login
  account listed in `DEMO_STUDENTS` — `demo_student` / "Laya Eshwarwak"
  (main) and `demo_student_1` / "Alex Carter" — and is the only
  committed source of their attempts. Both get the identical run: the
  RNG is re-seeded per student, so the two accounts show the same
  numbers and the choice of demo login is cosmetic. Each gets exactly
  one attempt per distinct AS Pure paper — a re-sit would add nothing
  under the counted-attempt rule — and the weak area is a subtopic
  carried by at least three DISTINCT papers, checked before seeding.
  Statistics still renders the true empty state, because `papers.csv`
  seeds no Statistics paper.
- **Action needed:** none. Both former PO questions are now moot: no id
  is reserved or special (accounts are matched by username, not id), and
  student 3's attempts are no longer orphaned — they are seeded and
  refreshed on every run. Adding a demo account is a line in
  `DEMO_STUDENTS` plus `python -m app.seed.set_password`.
