# Insight Engine

Source: BRD §10, §21, §22, §23. Deterministic, template-based.
**No LLM.** One insight per family.

## What it does

Selects exactly one approved template and fills it with the student's
actual stored values, describing the single most important current issue
for the subject.

## Approved templates (§21) — the ONLY allowed text

| Rule ID | Issue | Template |
|---|---|---|
| INS-01 | Low performance | `[Subtopic] is below your overall performance.` |
| INS-02 | Repeated errors | `You have made errors in [Subtopic] in [X] of your last [Y] relevant attempts.` |
| INS-03 | Declining | `Your recent performance in [Subtopic] is declining.` |
| INS-04 | Improving but weak | `Your performance in [Subtopic] is improving, but it remains below your overall average.` |
| INS-05 | Insufficient data | `More practice data is needed before OneView can reliably assess this area.` |

Placeholders in `[brackets]` are filled from stored/calculated values
only. No other text may be produced.

## Precedence (§23 — first match wins)

1. **Insufficient data** → INS-05. If required data is unavailable, use
   this and do NOT claim weakness. (Checked first, always.)
2. **Repeated errors** → INS-02, when a qualifying priority exists and
   the repeated-error signal is present.
3. **Declining** → INS-03, when the relevant subtopic trend is declining.
4. **Low performance** → INS-01, when the subtopic is materially below
   overall performance.
5. **Improving but weak** → INS-04, when improving but still below
   overall average.
6. No issue qualifies → a neutral approved insight or the configured
   no-priority state. Do NOT invent text.

## Which subtopic?

The insight describes the **top-ranked priority subtopic** for the
subject (from the priority engine). If there is no qualifying priority,
fall to rule 6.

## Function contract

    select_insight(subject_context: SubjectContext) -> Insight

- `subject_context`: scope-filtered aggregates plus the priority engine's
  output — data-sufficiency status, top priority subtopic, its trend,
  repeated-error X/Y counts, subtopic and subject averages.
- Returns an `Insight` with the rule ID used and the filled text. The
  rule ID must be stored for traceability (§10: every output traceable
  to a named rule).

## Test cases

- OV-T-017: repeated-error insight populated with actual X/Y values.
- OV-T-018: insufficient data → no fabricated insight (INS-05 only).

## What NOT to do

- Do not generate free-form text or call an LLM.
- Do not fill a template with prototype values — only stored data.
- Do not claim weakness when data is insufficient.
- Always record which rule ID produced the output.
