"""Tests for the recommendation engine — BRD §10, §24-25.

Agent: implement app/services/recommendation.py per
docs/specs/recommendation.md to make these pass.

Spec gap flagged, not guessed (CLAUDE.md: "if a spec is ambiguous, flag
it"): REC-04 (Inconsistent, §25 rule 4) has no INS-04 equivalent and,
per the spec, is only used "if an inconsistent signal is explicitly
computed; otherwise it is unused." No such signal exists anywhere in
this MVP — insight.SubjectContext has no `inconsistent_signal` field,
and no engine (insight/priority/trend) computes one — so
app/services/recommendation.py keeps REC-04's approved text for future
traceability but never selects it. This mirrors insight.py's own
INS-00 gap-handling and is a placeholder for the PO to confirm the
trigger, not to invent one.
"""

from __future__ import annotations

from app.services.insight import Insight, SubjectContext
from app.services.recommendation import (
    NO_RECOMMENDATION_RULE_ID,
    REC_TEXT,
    select_recommendation,
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


def _insight(rule_id, text="placeholder"):
    return Insight(rule_id=rule_id, text=text)


# --- §24 approved mapping — same issue insight selected (§25 rule 1) ---


def test_ins01_maps_to_rec01():
    out = select_recommendation(_insight("INS-01"), _ctx(subtopic_avg=54.0, subject_avg=70.0))
    assert out.rule_id == "REC-01"
    assert out.text == REC_TEXT["REC-01"]


def test_ins02_maps_to_rec02():
    out = select_recommendation(
        _insight("INS-02"),
        _ctx(repeated_error_signal=True, repeated_error_x=2, repeated_error_y=4),
    )
    assert out.rule_id == "REC-02"
    assert out.text == REC_TEXT["REC-02"]


def test_ins03_maps_to_rec03():
    out = select_recommendation(_insight("INS-03"), _ctx(trend_status="Needs Focus"))
    assert out.rule_id == "REC-03"
    assert out.text == REC_TEXT["REC-03"]


def test_ins04_maps_to_rec05():
    out = select_recommendation(_insight("INS-04"), _ctx(trend_status="Improving"))
    assert out.rule_id == "REC-05"
    assert out.text == REC_TEXT["REC-05"]


def test_ins05_maps_to_rec06():
    out = select_recommendation(
        _insight("INS-05"),
        _ctx(
            sufficient_data=False,
            subtopic=None,
            topic=None,
            subtopic_avg=None,
            subject_avg=None,
            trend_status=None,
        ),
    )
    assert out.rule_id == "REC-06"
    assert out.text == REC_TEXT["REC-06"]


# --- §25 rule 2: insufficient data always prevents a weakness rec ---


def test_insufficient_data_gives_rec06_never_a_weakness_rec():
    out = select_recommendation(
        _insight("INS-05"),
        _ctx(
            sufficient_data=False,
            subtopic=None,
            topic=None,
            subtopic_avg=None,
            subject_avg=None,
            trend_status=None,
        ),
    )
    assert out.rule_id == "REC-06"
    assert out.text == REC_TEXT["REC-06"]
    assert out.rule_id not in {"REC-01", "REC-02", "REC-03", "REC-04", "REC-05"}


def test_insufficient_data_wins_even_if_insight_disagrees():
    """Defensive check per §25 rule 2 ("REC-06 wins over any weakness
    rec"): even if `insight` were somehow stale/mismatched with a
    weakness rule id, sufficient_data=False on the context must still
    force REC-06 — mirrors insight.py's own defence against fabricating
    a weakness claim on insufficient data (OV-T-018)."""
    out = select_recommendation(
        _insight("INS-01"),
        _ctx(sufficient_data=False, repeated_error_signal=True, trend_status="Needs Focus"),
    )
    assert out.rule_id == "REC-06"
    assert out.text == REC_TEXT["REC-06"]


# --- §25 rule 3: repeated errors take precedence over low performance ---


def test_repeated_errors_beats_low_performance():
    out = select_recommendation(
        _insight("INS-02"),
        _ctx(
            repeated_error_signal=True,
            repeated_error_x=3,
            repeated_error_y=4,
            subtopic_avg=54.0,
            subject_avg=70.0,
        ),
    )
    assert out.rule_id == "REC-02"
    assert out.rule_id != "REC-01"


def test_repeated_errors_signal_wins_even_if_insight_disagrees():
    """Defensive check per §25 rule 3 / "what NOT to do": never use
    REC-01 when repeated errors qualify for REC-02, even if `insight`
    were mismatched with the context's signal."""
    out = select_recommendation(
        _insight("INS-01"),
        _ctx(repeated_error_signal=True, repeated_error_x=2, repeated_error_y=4),
    )
    assert out.rule_id == "REC-02"


# --- No issue qualifies (mirrors insight.py's INS-00 gap) ---


def test_no_issue_produces_no_fabricated_recommendation():
    out = select_recommendation(
        _insight("INS-00", text=None),
        _ctx(subtopic=None, topic=None, subtopic_avg=None, subject_avg=None, trend_status=None),
    )
    assert out.text is None
    assert out.rule_id == NO_RECOMMENDATION_RULE_ID


# --- Traceability (BRD §10: every output traceable to a named rule) ---


def test_rule_id_always_recorded():
    cases = [
        (_insight("INS-01"), _ctx(subtopic_avg=54.0, subject_avg=70.0)),
        (
            _insight("INS-02"),
            _ctx(repeated_error_signal=True, repeated_error_x=1, repeated_error_y=4),
        ),
        (_insight("INS-03"), _ctx(trend_status="Needs Focus")),
        (_insight("INS-04"), _ctx(trend_status="Improving")),
        (
            _insight("INS-05"),
            _ctx(
                sufficient_data=False,
                subtopic=None,
                topic=None,
                subtopic_avg=None,
                subject_avg=None,
                trend_status=None,
            ),
        ),
        (
            _insight("INS-00", text=None),
            _ctx(subtopic=None, topic=None, subtopic_avg=None, subject_avg=None, trend_status=None),
        ),
    ]
    for insight, ctx in cases:
        out = select_recommendation(insight, ctx)
        assert out.rule_id


# --- Only approved template text may ever be produced ---


def test_only_approved_templates_are_ever_produced():
    cases = [
        (_insight("INS-01"), _ctx(subtopic_avg=54.0, subject_avg=70.0)),
        (
            _insight("INS-02"),
            _ctx(repeated_error_signal=True, repeated_error_x=2, repeated_error_y=4),
        ),
        (_insight("INS-03"), _ctx(trend_status="Needs Focus")),
        (_insight("INS-04"), _ctx(trend_status="Improving")),
        (
            _insight("INS-05"),
            _ctx(
                sufficient_data=False,
                subtopic=None,
                topic=None,
                subtopic_avg=None,
                subject_avg=None,
                trend_status=None,
            ),
        ),
    ]
    for insight, ctx in cases:
        out = select_recommendation(insight, ctx)
        assert out.text in REC_TEXT.values() or out.text is None


def test_rec04_never_selected_in_mvp():
    """REC-04 (Inconsistent) has no computed signal anywhere in this MVP
    (§25 rule 4: "only use REC-04 if an inconsistent signal is
    explicitly computed; otherwise it is unused") — assert it never
    appears across the full set of insight rule ids the engine can
    receive."""
    for rule_id in ["INS-01", "INS-02", "INS-03", "INS-04", "INS-05", "INS-00"]:
        out = select_recommendation(
            _insight(rule_id, text=None),
            _ctx(
                repeated_error_signal=(rule_id == "INS-02"),
                sufficient_data=(rule_id != "INS-05"),
            ),
        )
        assert out.rule_id != "REC-04"
