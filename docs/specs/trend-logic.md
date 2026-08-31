# Trend Logic

Source: BRD §8, §15, §18. Statuses: **Improving**, **Stable**,
**Needs Focus**, plus a "More data needed" state.

## What it does

Classifies the direction of recent performance by comparing the average
of the latest 2 attempt percentages against the average of the previous
2, within one scope.

## Function contract

    classify_trend(percentages: list[float]) -> TrendResult

- `percentages`: valid attempt percentages in scope, ordered
  **oldest → newest**. Already filtered to (student, level, subject).
- Returns a `TrendResult` with a status and the delta, or a
  more-data-needed state.

## Algorithm (§15 — deterministic)

1. **Minimum data gate:** fewer than 4 valid attempts → status =
   `"More data needed"`. No definitive trend.
2. Take the latest 2 percentages → `latest_avg`.
3. Take the previous 2 percentages (positions 3rd- and 4th-from-newest)
   → `prev_avg`.
4. `delta = latest_avg − prev_avg` (in percentage points).
5. Classify:

| Condition | Status |
|---|---|
| delta ≥ +5.0 | Improving |
| delta ≤ −5.0 | Needs Focus |
| −4.99 ≤ delta ≤ +4.99 | Stable |

## Boundary cases (these are test cases — OV-T-009/010/011)

- delta exactly +5.0 → **Improving** (≥ is inclusive).
- delta exactly −5.0 → **Needs Focus** (≤ is inclusive).
- delta = +4.99 → Stable.
- delta = −4.99 → Stable.
- delta = 0 → Stable.

The inclusive boundary at exactly ±5 is the most common bug. Test it
explicitly.

## Chart vs classification

The trend **chart** displays all available recent attempt percentages
(even when < 4, where classification is withheld). The **classification**
follows the gate above. Chart and classification use the same
scope-filtered data (§15).

## What NOT to do

- Do not classify with fewer than 4 attempts.
- Do not use a different attempt set for the chart than for the
  classification.
- Do not read across levels or subjects.
