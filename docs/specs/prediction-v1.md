# Prediction V1 — Predicted Performance

Source: BRD §16, §7. User-facing label: **Predicted Performance**.
Internal method name: **Prediction V1** (never shown in UI).

## What it does

Forecasts the student's next-paper performance as a weighted average of
their most recent valid attempt percentages, weighting recent attempts
more heavily.

## Function contract

    predict_performance(attempts: list[AttemptPercentage],
                        config: PredictionConfig) -> PredictionResult

- `attempts`: valid attempts in scope, **already filtered** to
  (student, level, subject), each carrying a `percentage` and a
  `saved_at` timestamp. The function does not query — it receives data.
- Returns a `PredictionResult` with either a predicted percentage and a
  confidence flag, or an insufficient-data state.

## Weights (§16)

| Attempt position (most recent = 1) | Weight |
|---|---|
| 1 | 0.35 |
| 2 | 0.25 |
| 3 | 0.20 |
| 4 | 0.12 |
| 5 | 0.08 |

Weights sum to 1.00.

## Algorithm

1. Order attempts by `saved_at` **descending** (most recent first).
2. Take up to the 5 most recent.
3. **Sufficiency gate (OV-P-004):** default minimum is 5 completed valid
   attempts. If fewer than 5 and the "limited-data" config is disabled,
   return insufficient-data — no prediction.
4. If exactly 5: predicted % = Σ(percentage_i × weight_i).
5. **If fewer than 5 and limited-data is enabled (OV-P-005):** use only
   the weights for the positions present, **renormalise them to sum to
   1.0**, compute the weighted average, and mark `confidence = "limited"`.
   Never substitute a missing attempt with 0 (OV-P-005 acceptance).
6. Round the predicted percentage to 2 decimal places.

## Worked example (OV-P-002 — this is a test case)

Five most-recent percentages: 80, 84, 76, 88, 72 (position 1 → 5).

    80×0.35 + 84×0.25 + 76×0.20 + 88×0.12 + 72×0.08
    = 28.0 + 21.0 + 15.2 + 10.56 + 5.76
    = 80.52

Wait — verify against the BRD's stated answer of 80.08%. The BRD maps
the FIRST listed value to the MOST RECENT position. If the example list
"80, 84, 76, 88, 72" is oldest→newest, reverse it: most recent = 72.

    72×0.35 + 88×0.25 + 76×0.20 + 84×0.12 + 80×0.08
    = 25.2 + 22.0 + 15.2 + 10.08 + 6.4
    = 78.88   (not 80.08 either)

**ACTION FOR THE DEVELOPER:** the BRD states 80.08% for {80,84,76,88,72}
but does not state the ordering convention unambiguously. Before
implementing, confirm with the PO which value is "most recent". The test
`test_prediction.py::test_brd_worked_example` is written to expect
80.08% and is marked xfail until the ordering is confirmed — do not
"fix" the numbers to force a pass. This ambiguity is real and must be
resolved by the spec owner, not the agent.

## Mark-scale conversion (OV-P-003)

The predicted percentage is displayed against the relevant assessment
mark scale. Do NOT assume a universal max mark (e.g. 75). Convert using
the max marks of the scope's papers. For MVP, present the percentage as
primary and the mark range as derived.

## Empty / insufficient states

- 0 attempts → "No prediction yet — record practice papers to begin."
- 1–4 attempts, limited-data disabled → "More data needed for a
  prediction (5 papers recommended)."
- 1–4 attempts, limited-data enabled → prediction shown with a
  "limited confidence" marker.

## What NOT to do

- Do not zero-fill missing attempts.
- Do not display "Prediction V1" in the UI.
- Do not read across levels or subjects.
- Do not hard-code 75 as the max mark.
