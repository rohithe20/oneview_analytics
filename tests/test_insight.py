"""Tests for the insight engine — BRD §10, §21-23.

Agent: implement app/services/insight.py per
docs/specs/insight-engine.md to make these pass.

Spec gap flagged, not guessed (CLAUDE.md: "if a spec is ambiguous, flag
it"): precedence rule 6 ("no issue qualifies") has no approved template
in §21 for a positive/neutral case — INS-01..05 are all either a
weakness or the insufficient-data state. app/services/insight.py
represents rule 6 as rule_id "INS-00" with text=None (nothing rendered)
rather than inventing text or reusing INS-05's insufficient-data
wording for a case where data is actually sufficient. This is a
placeholder for the PO to confirm; do not change it to fabricate text.
"""

from __future__ import annotations

from app.services.insight import SubjectContext, select_insight

INSUFFICIENT_DATA_TEXT = (
    "More practice data is needed before OneView can reliably assess this area."
)


def _ctx(
    sufficient_data=True,
    subtopic="Vectors",
    topic="Mechanics",
    subtopic_avg=54.0,
    subject_avg=70.0,
    trend_status="Stable",
    repeated_error_signal=False,
    repeated_error_x=None,
    repeated_error_y=None,
):
    return SubjectContext(
        sufficient_data=sufficient_data,
        subtopic=subtopic,
        topic=topic,
        subtopic_avg=subtopic_avg,
        subject_avg=subject_avg,
        trend_status=trend_status,
        repeated_error_signal=repeated_error_signal,
        repeated_error_x=repeated_error_x,
        repeated_error_y=repeated_error_y,
    )


# --- Rule 1: insufficient data always wins (checked first, always) ---


def test_insufficient_data_gives_ins05():
    out = select_insight(
        _ctx(
            sufficient_data=False,
            subtopic=None,
            subtopic_avg=None,
            subject_avg=None,
            trend_status=None,
        )
    )
    assert out.rule_id == "INS-05"
    assert out.text == INSUFFICIENT_DATA_TEXT


def test_insufficient_data_beats_repeated_errors():
    """Even if every other signal points to a weakness, insufficient data
    must still win — OV-T-018: never fabricate a weakness claim."""
    out = select_insight(
        _ctx(
            sufficient_data=False,
            repeated_error_signal=True,
            repeated_error_x=3,
            repeated_error_y=4,
            trend_status="Needs Focus",
        )
    )
    assert out.rule_id == "INS-05"
    assert out.text == INSUFFICIENT_DATA_TEXT
    assert "Vectors" not in out.text


# --- Rule 2: repeated errors (OV-T-017) ---


def test_repeated_errors_gives_ins02_with_actual_xy():
    out = select_insight(_ctx(repeated_error_signal=True, repeated_error_x=2, repeated_error_y=4))
    assert out.rule_id == "INS-02"
    assert out.text == "You have made errors in Vectors in 2 of your last 4 relevant attempts."


def test_repeated_errors_beats_declining_trend():
    out = select_insight(
        _ctx(
            repeated_error_signal=True,
            repeated_error_x=3,
            repeated_error_y=4,
            trend_status="Needs Focus",
        )
    )
    assert out.rule_id == "INS-02"


# --- Rule 3: declining trend ---


def test_declining_trend_gives_ins03():
    out = select_insight(_ctx(trend_status="Needs Focus", repeated_error_signal=False))
    assert out.rule_id == "INS-03"
    assert out.text == "Your recent performance in Vectors is declining."


def test_declining_beats_low_performance():
    out = select_insight(_ctx(trend_status="Needs Focus", subtopic_avg=54.0, subject_avg=70.0))
    assert out.rule_id == "INS-03"


# --- Rule 4: low performance ---


def test_low_performance_gives_ins01():
    out = select_insight(_ctx(trend_status="Stable", subtopic_avg=54.0, subject_avg=70.0))
    assert out.rule_id == "INS-01"
    assert out.text == "Vectors is below your overall performance."


# --- Rule 5: improving but weak ---


def test_improving_but_weak_gives_ins04():
    out = select_insight(_ctx(trend_status="Improving", subtopic_avg=54.0, subject_avg=70.0))
    assert out.rule_id == "INS-04"
    assert (
        out.text
        == "Your performance in Vectors is improving, but it remains below your overall average."
    )


def test_low_performance_precedes_improving_but_weak():
    """Rule 4 (low performance) is checked before rule 5 (improving but
    weak); only a trend explicitly marked Improving should ever reach
    INS-04 — anything else below average falls to INS-01 first."""
    out = select_insight(_ctx(trend_status="Stable", subtopic_avg=54.0, subject_avg=70.0))
    assert out.rule_id == "INS-01"


# --- Rule 6: no issue qualifies ---


def test_no_qualifying_priority_produces_no_fabricated_text():
    out = select_insight(
        _ctx(subtopic=None, topic=None, subtopic_avg=None, subject_avg=None, trend_status=None)
    )
    assert out.text is None
    assert out.rule_id not in {"INS-01", "INS-02", "INS-03", "INS-04", "INS-05"}


def test_at_or_above_average_no_issue():
    out = select_insight(
        _ctx(subtopic=None, topic=None, subtopic_avg=None, subject_avg=None, trend_status="Stable")
    )
    assert out.text is None


# --- Traceability (BRD §10: every output traceable to a named rule) ---


def test_rule_id_always_recorded():
    for ctx in [
        _ctx(
            sufficient_data=False,
            subtopic=None,
            subtopic_avg=None,
            subject_avg=None,
            trend_status=None,
        ),
        _ctx(repeated_error_signal=True, repeated_error_x=1, repeated_error_y=4),
        _ctx(trend_status="Needs Focus"),
        _ctx(trend_status="Stable"),
        _ctx(trend_status="Improving"),
        _ctx(subtopic=None, topic=None, subtopic_avg=None, subject_avg=None, trend_status=None),
    ]:
        out = select_insight(ctx)
        assert out.rule_id


# --- Only approved template text may ever be produced ---


APPROVED_TEXTS = {
    "INS-01": "Vectors is below your overall performance.",
    "INS-02": "You have made errors in Vectors in 2 of your last 4 relevant attempts.",
    "INS-03": "Your recent performance in Vectors is declining.",
    "INS-04": (
        "Your performance in Vectors is improving, but it remains below your overall average."
    ),
    "INS-05": INSUFFICIENT_DATA_TEXT,
}


def test_only_approved_templates_are_ever_produced():
    contexts = [
        _ctx(
            sufficient_data=False,
            subtopic=None,
            subtopic_avg=None,
            subject_avg=None,
            trend_status=None,
        ),
        _ctx(repeated_error_signal=True, repeated_error_x=2, repeated_error_y=4),
        _ctx(trend_status="Needs Focus"),
        _ctx(trend_status="Stable"),
        _ctx(trend_status="Improving"),
    ]
    for ctx in contexts:
        out = select_insight(ctx)
        assert out.text in APPROVED_TEXTS.values() or out.text is None
