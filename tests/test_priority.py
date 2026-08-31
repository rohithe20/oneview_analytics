"""Tests for the priority engine — BRD §19-20. The classification rules
and the tie-break order are the two things to get right.

Agent: implement app/services/priority.py per
docs/specs/priority-engine.md to make these pass.

Scope note: the field named `subject_avg` here is the overall average
for the current COMPONENT FAMILY (Pure or Statistics), not a separate
subject. The subject is always Maths. Keep the field name or rename to
`family_avg` consistently across the module and these tests — but do it
in one deliberate change, not piecemeal.
"""
from __future__ import annotations

from app.services.priority import SubtopicStats, rank_priorities


def _stat(
    subtopic="Vectors",
    topic="Mechanics",
    subtopic_avg=50.0,
    subject_avg=70.0,
    observation_count=5,
    repeated_error_signal=False,
    improving=False,
    recent_error_frequency=0.0,
):
    return SubtopicStats(
        topic=topic,
        subtopic=subtopic,
        subtopic_avg=subtopic_avg,
        subject_avg=subject_avg,
        observation_count=observation_count,
        repeated_error_signal=repeated_error_signal,
        improving=improving,
        recent_error_frequency=recent_error_frequency,
    )


# --- Stage 1: classification (OV-T-012 .. OV-T-015) ---

def test_gap_16_is_high():
    # gap = 70 - 54 = 16
    out = rank_priorities([_stat(subtopic_avg=54, subject_avg=70)])
    assert out[0].priority == "High"


def test_gap_10_with_repeated_errors_is_high():
    out = rank_priorities(
        [_stat(subtopic_avg=60, subject_avg=70, repeated_error_signal=True)]
    )
    assert out[0].priority == "High"


def test_gap_10_without_repeated_errors_is_medium():
    out = rank_priorities(
        [_stat(subtopic_avg=60, subject_avg=70, repeated_error_signal=False)]
    )
    assert out[0].priority == "Medium"


def test_fewer_than_three_observations_no_priority():
    out = rank_priorities([_stat(subtopic_avg=40, subject_avg=70, observation_count=2)])
    assert out == []  # not classified as weak


def test_at_or_above_average_no_priority():
    out = rank_priorities([_stat(subtopic_avg=75, subject_avg=70, improving=True)])
    assert out == []


def test_small_gap_is_monitor():
    # gap = 3
    out = rank_priorities([_stat(subtopic_avg=67, subject_avg=70)])
    assert out[0].priority == "Monitor"


# --- Stage 2: ranking and tie-breaks (OV-T-016) ---

def test_high_ranked_above_medium():
    high = _stat(subtopic="A", subtopic_avg=54, subject_avg=70)      # gap 16 High
    medium = _stat(subtopic="B", subtopic_avg=60, subject_avg=70)    # gap 10 Medium
    out = rank_priorities([medium, high])
    assert [p.subtopic for p in out] == ["A", "B"]


def test_tiebreak_by_largest_gap():
    a = _stat(subtopic="A", subtopic_avg=54, subject_avg=70)  # gap 16
    b = _stat(subtopic="B", subtopic_avg=50, subject_avg=70)  # gap 20
    out = rank_priorities([a, b])
    assert [p.subtopic for p in out] == ["B", "A"]  # larger gap first


def test_tiebreak_by_error_frequency_when_gap_equal():
    a = _stat(subtopic="A", subtopic_avg=54, subject_avg=70, recent_error_frequency=0.3)
    b = _stat(subtopic="B", subtopic_avg=54, subject_avg=70, recent_error_frequency=0.6)
    out = rank_priorities([a, b])
    assert [p.subtopic for p in out] == ["B", "A"]  # higher error freq first


def test_returns_at_most_three():
    stats = [
        _stat(subtopic=f"S{i}", subtopic_avg=50 - i, subject_avg=70)
        for i in range(6)
    ]
    out = rank_priorities(stats)
    assert len(out) == 3


def test_returns_fewer_when_fewer_qualify():
    out = rank_priorities([_stat(subtopic_avg=54, subject_avg=70)])
    assert len(out) == 1
