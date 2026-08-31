from __future__ import annotations

from dataclasses import dataclass

INSUFFICIENT_DATA_TEXT = (
    "More practice data is needed before OneView can reliably assess this area."
)

# Rule 6 (§23): "no issue qualifies" has no approved template in §21 — every
# listed template is either a weakness or the insufficient-data state, and
# none fits a sufficient-data / nothing-to-flag case. Rather than reuse
# INS-05's wording (which would misrepresent sufficient data as insufficient)
# or invent new text, this is modelled as a distinct rule with no rendered
# text. Flagged for the PO per CLAUDE.md — do not fabricate text here.
NO_INSIGHT_RULE_ID = "INS-00"

DECLINING_TREND_STATUS = "Needs Focus"
IMPROVING_TREND_STATUS = "Improving"
LOW_PERFORMANCE_GAP_THRESHOLD = 0.0


@dataclass
class SubjectContext:
    sufficient_data: bool
    subtopic: str | None = None
    topic: str | None = None
    subtopic_avg: float | None = None
    subject_avg: float | None = None
    trend_status: str | None = None
    repeated_error_signal: bool = False
    repeated_error_x: int | None = None
    repeated_error_y: int | None = None


@dataclass
class Insight:
    rule_id: str
    text: str | None


def select_insight(subject_context: SubjectContext) -> Insight:
    """Select the single approved insight template per BRD §21-23.

    `subject_context` carries the top-ranked priority subtopic (from the
    priority engine) plus its trend and repeated-error signal, already
    scope-filtered. Precedence is first-match-wins: insufficient data,
    then repeated errors, then declining, then low performance, then
    improving-but-weak, else no issue qualifies.
    """
    ctx = subject_context

    if not ctx.sufficient_data:
        return Insight(rule_id="INS-05", text=INSUFFICIENT_DATA_TEXT)

    if ctx.subtopic is None:
        return Insight(rule_id=NO_INSIGHT_RULE_ID, text=None)

    if ctx.repeated_error_signal:
        text = (
            f"You have made errors in {ctx.subtopic} in {ctx.repeated_error_x} "
            f"of your last {ctx.repeated_error_y} relevant attempts."
        )
        return Insight(rule_id="INS-02", text=text)

    if ctx.trend_status == DECLINING_TREND_STATUS:
        return Insight(
            rule_id="INS-03", text=f"Your recent performance in {ctx.subtopic} is declining."
        )

    gap = (ctx.subject_avg or 0.0) - (ctx.subtopic_avg or 0.0)
    below_average = gap > LOW_PERFORMANCE_GAP_THRESHOLD

    if below_average and ctx.trend_status != IMPROVING_TREND_STATUS:
        return Insight(rule_id="INS-01", text=f"{ctx.subtopic} is below your overall performance.")

    if below_average and ctx.trend_status == IMPROVING_TREND_STATUS:
        return Insight(
            rule_id="INS-04",
            text=(
                f"Your performance in {ctx.subtopic} is improving, but it remains "
                "below your overall average."
            ),
        )

    return Insight(rule_id=NO_INSIGHT_RULE_ID, text=None)


__all__ = ["SubjectContext", "Insight", "select_insight"]
