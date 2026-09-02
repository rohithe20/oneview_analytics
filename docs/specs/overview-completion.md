# Overview Completion Checklist

This is the authoritative "done" definition for the Overview page. Every
item must be verifiably true and traceable to the BRD / overview-ui.md.
Agents: when a task references this file, treat each checkbox as a
requirement, not a suggestion. Do not mark work complete unless the
listed condition holds. If a requirement conflicts with the code or is
ambiguous, STOP and flag it in Open Items — do not guess.

Scope for this phase: full Overview functionality, both families, all
states. PO-gated open items (below) are explicitly OUT and stay parked.

---

## A. Rendering — every value visible and correct

- [ ] A1. Predicted Performance card shows the percentage as primary;
      label is exactly "Predicted Performance" (never "Prediction V1").
- [ ] A2. "limited confidence" chip shows only when confidence is limited.
- [ ] A3. Trend card renders a Chart.js line chart of `trend_points` per
      family. Chart.js loaded from CDN; one canvas per family; chart
      shows available points even when classification is withheld.
- [ ] A4. Trend status pill shows Improving / Stable / Needs Focus /
      More data needed, coloured per band (§ overview-ui §2).
- [ ] A5. All numeric values are coloured by threshold: emerald ≥75,
      amber 50–74, rose <50 — bound to the value, never hardcoded.
- [ ] A6. Priority Areas: up to 3 rows, each topic + subtopic + % + tag
      (High rose / Medium amber / Monitor slate). When topic == subtopic
      show the name once (no "X → X").
- [ ] A7. Topic performance uses meaningful colour bands (strong/
      moderate/weak) wherever a per-topic bar/indicator is shown.
- [ ] A8. Insight card shows exactly one approved template string, or is
      omitted per the no-issue rule — never invented copy.
- [ ] A9. Recommendation card shows one approved string, or omitted —
      never invented copy.

## B. States — all three, every component

For EACH of the six components (prediction, metrics, trend, priority,
insight, recommendation), verify all three render correctly:

- [ ] B1. Populated — real values (test with the ≥5-attempt Pure scope).
- [ ] B2. Insufficient data — explicit honest message, no fabricated
      number, never shown as weakness. (Test with the <5-attempt
      Statistics scope.)
- [ ] B3. Empty — a scope with zero attempts shows a "record a paper to
      begin" prompt, not a blank box or an error.
- [ ] B4. Per-engine gates respected: trend needs ≥4 attempts to
      classify; priority needs ≥3 observations per subtopic; overall
      gate is ≥5 for definitive prediction/priority.

## C. Scope behaviour — the BRD's hardest rule (§32)

- [ ] C1. The AS/A Level selector re-scopes the ENTIRE page. After
      switching, every card/chart/priority/insight reflects the new
      level with NO stale data from the other level.
- [ ] C2. Pure and Statistics render side by side and are never combined
      into one score.
- [ ] C3. Every panel reads only its own scope
      (student_id, exam_level, component_family). No cross-scope leak.

## D. Interaction

- [ ] D1. Each Priority row is clickable and links toward Topic Analysis
      for that topic/subtopic (OV-T-019). A stub target route is
      acceptable for now, but the link must be present and carry the
      topic/subtopic context.
- [ ] D2. Target-setting control (§35): the student can set a practice
      target per (level, family). Validated 0 ≤ target ≤ available
      papers (OV-PL-003). Setting it updates Papers Completed / Target
      and the completion bar. Target = 0 shows a not-set state, never a
      divide-by-zero (OV-PL-006).

## E. Shell / consistency (§ overview-ui §1, §7)

- [ ] E1. One shared shell (base.html); sidebar + header only once.
- [ ] E2. Active nav = Overview; Record / Topic Analysis present;
      post-MVP nav items disabled or omitted.
- [ ] E3. Palette matches overview-ui §2 (violet primary, slate
      surfaces, meaningful strong/moderate/weak colour).

---

## OUT of scope for this phase (PO-gated — do NOT build or guess)

Tracked in Open Items; each needs a PO decision:
- Prediction worked-example ordering (xfail test stays).
- Insight/Recommendation copy for "sufficient data, no issue qualifies".
- Predicted-performance mark-range secondary display (needs a
  total-marks source; percentage-only is current behaviour).
- Real Statistics seed data (Statistics column demoing as
  insufficient-data state is acceptable; do not fabricate Statistics
  topics to fill it).

Building any of these without a PO decision is a spec violation. Leave
them parked.

## Verification command reference

    uv run pytest                 # all green, no test edits
    uv run ruff check .
    uv run uvicorn app.main:app --reload   # then click through B/C/D by hand
