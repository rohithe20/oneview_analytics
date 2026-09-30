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

## Record write path — "Date Completed" overlaps the existing `completed_at`

- **Status:** open, needs PO/spec confirmation
- **Where:** `docs/specs/record-service.md` §"Schema note"; migration
  `7c4c306f3eca`; `app/services/record.py` `_as_completed_at`
- **Issue:** the spec says to add `attempts.date_completed` if the BRD's
  "Date Completed" isn't on the model. `attempts.completed_at` already
  existed and is a *different* thing: a timestamptz that every analytics
  view orders by (`v_latest_paper_attempts`'s
  `ORDER BY completed_at DESC NULLS LAST`, `v_attempt_totals`,
  `app/services/overview.py`). The BRD field is the date the student
  states on the form.
- **Current behaviour:** both columns exist and `save_attempt` writes
  BOTH from the one input — `date_completed` as given, `completed_at` as
  midnight UTC on that date. Writing only the new column would have left
  `completed_at` NULL, sorting a freshly recorded attempt LAST and making
  every engine ignore the newest result.
- **Action needed:** PO/spec confirms two columns is intended, or the
  columns are collapsed into one (which means migrating the existing
  demo/seed rows and every view that names `completed_at`).

## Record write path — §12 rules the list under-specifies

- **Status:** open, needs PO confirmation; implemented under the readings below
- **Where:** `docs/specs/record-service.md` §12 table; `app/services/record.py`
- **Issues and readings taken** (all documented in the service's module
  docstring and covered by `tests/test_record.py`):
  - **RP-V-004** ("Marks Lost blank on any row") is read as requiring an
    entry for EVERY sub-part of the paper — a missing row is a blank row.
    This is also what keeps the write path consistent with
    `v_attempt_totals`, which derives the denominator by summing
    `max_marks` over the sub-parts that HAVE result rows: a partial
    submission would make the analytics disagree with the total the
    service returned, breaking BRD §32 rule 8. Note this forecloses a
    partial/draft save through this function.
  - **RP-V-010** ("Total Marks Lost > 75") is enforced against the
    paper's stated `papers.total_marks`, not the literal 75 (BRD §32
    rule 3). With consistent reference data RP-V-006 already caps the
    total at the sum of `max_marks`, so RP-V-010 only ever fires when a
    paper's sub-parts over-sum the scale they are marked out of — i.e.
    it is a reference-data guard, not a rule a student can trip.
    `RecordResult.total_marks` is the summed `max_marks` (the spec's
    "ideally SUM(max_marks) as a check").
  - **RP-V-008** ("force No Error (or reject)") is implemented as
    **reject**, matching the spec's own §8 wording ("Reject anything
    else") rather than silently rewriting what the student submitted.
  - **RP-V-011 idempotency:** the service rejects a payload naming the
    same sub-part twice (the `UNIQUE(attempt_id, sub_part_id)` case the
    spec cites). Attempt-level double-submit protection is left to the
    page's submit-disable, per the spec's "a submit-token or
    button-disable is acceptable for MVP" — **flagging that as the
    approach chosen**; no token column was introduced. If the PO wants
    server-side protection, that needs a schema decision.
  - **Changing the paper on an edit** is rejected (RP-V-001). The spec
    covers "correcting a paper" as correcting the marks; re-pointing an
    attempt at a different paper would orphan every result row against
    the old paper's sub-parts. Correcting a wrong paper choice therefore
    means recording the right paper, not mutating the existing attempt.
  - **Ownership failure on edit** raises `AttemptNotFoundError`, the same
    error as a missing attempt, so a caller cannot learn that an attempt
    it may not touch exists (§19). It is raised on its own rather than
    collected with the RP-V-* list, being an authorization failure and
    not a form violation.
  - **Percentage precision:** carried at 2dp to match `v_attempt_totals`'
    `ROUND(…, 2)`, so the service and the analytics report the same
    number for the same attempt. RP-T-011's "90.7%" is that value
    (90.67) displayed to one place.
- **Action needed:** PO confirms these readings, or the spec's §12 table
  is tightened so the next write-path change doesn't re-litigate them.

## Record page — "Variant" means the paper code (41/42/43), not the stored variant digit

- **Status:** resolved — PO chose the combined `component||variant`
  display code; implemented
- **Where:** BRD §6 ("Example variants: 41, 42, 43"), §25.1, RP-T-005;
  `app/services/paper_catalog.variant_code`,
  `app/web/templates/partials/paper_options.html`
- **Issue:** the BRD's example variant values are two-digit Cambridge
  paper codes — component digit followed by variant digit (41 = the
  Mechanics component, variant 1). This schema splits those: the
  component is carried by Paper Type (`papers.component`) and the
  variant by `papers.variant`.
- **PO decision:** anywhere a variant is shown on the Record page it
  displays as the combined two-digit code (component 1, variant 2 ->
  "12"), matching the paper reference the page already renders
  ("9709/12"). Not the bare split digit.
- **Current behaviour:** `variant_code(component, variant)` centralises
  the rule; the Variant dropdown label uses it, so component 1's
  variants show as 11/12/13/15. Only the DISPLAY is combined — the
  option's stored VALUE remains the bare `papers.variant`, so
  `resolve_selection`'s membership checks and the eventual save are
  unchanged. Covered by `tests/test_record_page.py`
  (`test_variant_code_is_the_component_and_variant_digits`,
  `test_variants_are_shown_as_combined_paper_codes`).
- **Action needed:** none.

## Record page — "Session" needs the year to identify a paper

- **Status:** open, needs PO/spec confirmation
- **Where:** BRD §6 ("Values come from available sessions for the
  selected paper"); `app/services/paper_catalog.SessionOption`
- **Issue:** §6 names Session and Variant as the only fields between
  Paper Type and the paper, but a paper's identity in the data model is
  subject + component + variant + session + **year**. "May/June" alone
  does not select a paper once the seed holds more than one year.
- **Current behaviour:** each Session option is a session/year pair
  ("May/June 2025", newest first), with a `SESSION-YEAR` form value.
  This keeps §6's five fields intact rather than adding a sixth Year
  dropdown the BRD does not list.
- **Action needed:** PO confirms session+year in one dropdown, or asks
  for a separate Year field (which would change the §6/§25.1 field
  order).

## Record page — the global AS/A toggle navigates away from an in-progress entry

- **Status:** partly addressed with the question table — guarded by a
  confirmation; the toggle's target is still a PO decision
- **Where:** `app/web/templates/base.html` header;
  `app/web/templates/record.html` (unsaved-changes guard); BRD §5
  ("Global context is visible; the page also has its own Level field
  for the paper record")
- **Issue:** the shared header's Exam Level toggle links to
  `/overview?level=...`, because that is the control overview-ui.md §3
  defines as driving the Overview page. On Record it therefore leaves
  the page, and now that the question table and Marks Lost inputs
  exist, one click could discard unsaved entry.
- **Current behaviour:** base.html is unchanged, but discarding entered
  marks now warns first. The Record page carries a guard (record.html):
  a `beforeunload` handler covers real navigations (refresh, tab close,
  the POST logout, an external link) and an `htmx:confirm` handler
  covers in-app boosted navigation and the Paper Details Level select,
  which swap the table out. "Dirty" is read live from the DOM (any
  Marks Lost input with a value), so a blank or freshly loaded table
  never prompts, and the live Results Summary recalc — fired by the
  marks inputs themselves — is exempted so it never triggers the
  dialog. This covers the header AS/A toggle too, because it is a
  boosted `<a>`.
- **Action needed:** the "warn before discarding" requirement is met.
  Still a PO decision whether, on Record specifically, the header
  toggle should become read-only context or point at `/record?level=`
  instead of `/overview?level=` — the guard makes it safe either way,
  but it still routes to Overview today.

## Record page — HTMX fragments and the login redirect

- **Status:** open, low priority
- **Where:** `app/main.redirect_to_login`;
  `app/web/partials/record_paper.py`
- **Issue:** `NotAuthenticatedError` returns a 303 to `/login`. A normal
  navigation follows it correctly, but an HTMX fragment request whose
  session has expired follows the redirect too and swaps the login
  page's HTML into `#paper-options`.
- **Current behaviour:** the fragment route is protected and the
  redirect is correct; only the swap target is wrong. Not reachable
  without an expiry mid-session.
- **Action needed:** when convenient, have the handler answer an
  `HX-Request` with an `HX-Redirect` header instead of a 303. Deferred
  here because it changes a shared handler that every protected route
  uses, which is outside this task's file scope.

## Record page — A Level and Statistics dead-end in the selection chain

- **Status:** open — same root cause as "Seed data — no Statistics-family
  topics" above
- **Where:** `app/seed/data/papers.csv`; the Paper Type dropdown
- **Issue:** the seed holds only AS Pure papers, so selecting A Level
  offers no Paper Type at all, and Statistics is absent at both levels.
  RP-T-003 ("Select A → Paper 3 - Pure Mathematics 2 and Paper 5 -
  Probability & Statistics 2") cannot be demonstrated against the seed;
  it is covered in `tests/test_record_page.py` with purpose-built
  reference data instead.
- **Current behaviour:** the page shows the honest §18 "no valid paper
  structure" message rather than offering a paper type with no papers
  behind it.
- **Action needed:** none new — unblocks when the Statistics/A Level
  seed item above is resolved.
