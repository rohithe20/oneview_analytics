from __future__ import annotations

from dataclasses import dataclass

from app.services.insight import Insight, SubjectContext

REC_TEXT = {
    "REC-01": (
        "Review the concept; practise targeted questions; reattempt similar past-paper questions."
    ),
    "REC-02": "Review recent errors; practise the same skill; reattempt similar questions.",
    "REC-03": "Targeted practice before the next full paper; review mistakes afterward.",
    "REC-04": "Mixed practice + timed questions.",
    "REC-05": "Continue targeted practice; reassess after more attempts.",
    "REC-06": "More relevant practice required; no weakness recommendation yet.",
}

# §25 rule 4: REC-04 (Inconsistent) has no INS-04 equivalent, and per CLAUDE.md
# ("if a spec is ambiguous, flag it — do not guess") no "inconsistent" signal
# is computed anywhere in this MVP's engines (insight/priority/trend) —
# SubjectContext carries no such field. The approved text stays in REC_TEXT
# above for traceability if that signal is ever added, but no branch below
# selects REC-04. Flagged for the PO, same treatment as insight.py's INS-00 gap.

# Mirrors insight.py's NO_INSIGHT_RULE_ID: when the insight engine found no
# qualifying issue (INS-00), there is no approved recommendation text either.
NO_RECOMMENDATION_RULE_ID = "REC-00"

_INSIGHT_TO_RECOMMENDATION = {
    "INS-03": "REC-03",
    "INS-01": "REC-01",
    "INS-04": "REC-05",
}


@dataclass
class Recommendation:
    rule_id: str
    text: str | None


def select_recommendation(insight: Insight, subject_context: SubjectContext) -> Recommendation:
    """Map the Insight Engine's selected issue to its approved recommendation per BRD §24-25.

    Follows `insight`'s decision (§25 rule 1) except for two defensive
    checks the spec calls out explicitly, applied ahead of the plain
    mapping: insufficient data always prevents a weakness recommendation
    (§25 rule 2), and a repeated-error signal always takes precedence
    over generic low-performance practice (§25 rule 3) — checked
    directly against `subject_context`, not solely trusted from
    `insight`, in case the two ever disagree.
    """
    ctx = subject_context

    if not ctx.sufficient_data or insight.rule_id == "INS-05":
        return Recommendation(rule_id="REC-06", text=REC_TEXT["REC-06"])

    if ctx.repeated_error_signal or insight.rule_id == "INS-02":
        return Recommendation(rule_id="REC-02", text=REC_TEXT["REC-02"])

    rec_id = _INSIGHT_TO_RECOMMENDATION.get(insight.rule_id)
    if rec_id:
        return Recommendation(rule_id=rec_id, text=REC_TEXT[rec_id])

    return Recommendation(rule_id=NO_RECOMMENDATION_RULE_ID, text=None)


__all__ = ["Recommendation", "select_recommendation", "REC_TEXT", "NO_RECOMMENDATION_RULE_ID"]
