# Recommendation Engine

Source: BRD §10, §24, §25. Deterministic, mapping-based. **No LLM.**
One recommendation per family.

## What it does

Maps the issue selected by the Insight Engine to an approved
recommendation. It does not re-derive the issue — it follows the
insight's decision unless the mapping explicitly requires otherwise.

## Approved mappings (§24) — the ONLY allowed text

| Rule ID | Detected issue | Recommendation |
|---|---|---|
| REC-01 | Low performance | Review the concept; practise targeted questions; reattempt similar past-paper questions. |
| REC-02 | Repeated errors | Review recent errors; practise the same skill; reattempt similar questions. |
| REC-03 | Declining | Targeted practice before the next full paper; review mistakes afterward. |
| REC-04 | Inconsistent | Mixed practice + timed questions. |
| REC-05 | Improving but weak | Continue targeted practice; reassess after more attempts. |
| REC-06 | Insufficient data | More relevant practice required; no weakness recommendation yet. |

## Precedence (§25)

1. Apply the same issue the Insight Engine selected, mapping insight →
   recommendation:
   - INS-05 → REC-06
   - INS-02 → REC-02
   - INS-03 → REC-03
   - INS-01 → REC-01
   - INS-04 → REC-05
2. **Insufficient data always prevents a weakness recommendation**
   (REC-06 wins over any weakness rec).
3. **Repeated errors take precedence** over generic low-performance
   practice when both are present (REC-02 over REC-01).
4. REC-04 (Inconsistent) is available for the inconsistent-performance
   case where the mapping requires it, even though there is no INS-04
   equivalent — this is the one place recommendation diverges from
   insight. For MVP, only use REC-04 if an "inconsistent" signal is
   explicitly computed; otherwise it is unused.

## Function contract

    select_recommendation(insight: Insight,
                          subject_context: SubjectContext) -> Recommendation

- Takes the Insight Engine's output plus the same scope context.
- Returns a `Recommendation` with the rule ID and the approved text.
  Rule ID stored for traceability.

## Test cases

- Covered alongside insight in OV-T-017 / OV-T-018.
- Add: INS-02 present → REC-02 selected, not REC-01.
- Add: insufficient data → REC-06, never a weakness recommendation.

## What NOT to do

- Do not generate free-form recommendations.
- Do not give a weakness recommendation on insufficient data.
- Do not use REC-01 when repeated errors qualify for REC-02.
- Always record the rule ID.
