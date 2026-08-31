# QA Acceptance Matrix

Source: BRD §30. Each row is a test that must pass. Agents: when you
build an engine, the matching tests here are your definition of done.
These map directly to the `tests/test_*.py` files.

| Test ID | Scenario | Expected | Engine |
|---|---|---|---|
| OV-T-001 | Open Overview, AS selected | Only AS data; PM + Stats side-by-side | scope |
| OV-T-002 | Switch AS → A | All cards/charts/priorities/insights refresh to A | scope |
| OV-T-003 | Target 30, completed 18 | Completion 60%; available count irrelevant | planning |
| OV-T-004 | Target 0 | No divide-by-zero; not-set state | planning |
| OV-T-005 | Average calculation | Avg score and % match dataset | metrics |
| OV-T-006 | Recent score | Most recent valid attempt shown | metrics |
| OV-T-007 | Five prediction attempts | Weighted 35/25/20/12/8 | prediction |
| OV-T-008 | ≤4 prediction attempts | No definitive prediction unless limited-data rule; never zero-fill | prediction |
| OV-T-009 | Trend +5pp boundary | Improving | trend |
| OV-T-010 | Trend −5pp boundary | Needs Focus | trend |
| OV-T-011 | Trend within ±4.99pp | Stable | trend |
| OV-T-012 | Subtopic gap 16pp, ≥3 obs | High | priority |
| OV-T-013 | Gap 10pp + repeated errors ≥50% | High | priority |
| OV-T-014 | Gap 10pp, no repeated errors | Medium | priority |
| OV-T-015 | Subtopic < 3 observations | No weak classification; more-data state | priority |
| OV-T-016 | Tie between priorities | Tie-breaks in documented order | priority |
| OV-T-017 | Repeated-error insight | Approved template with actual X/Y | insight |
| OV-T-018 | Insufficient data | No fabricated weakness/prediction/insight/rec | all |
| OV-T-019 | Click priority | Topic Analysis opens with correct topic/subtopic | ui |
| OV-T-020 | Correct saved attempt | Analytics update; attempt count not duplicated | write path |
