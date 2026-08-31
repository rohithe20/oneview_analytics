"""Tests for Prediction V1 — written from BRD §16 before the engine exists.

The agent's job: make these pass by implementing
app/services/prediction.py per docs/specs/prediction-v1.md.
Do NOT edit expected values to force a pass. If the BRD worked example
(test_brd_worked_example) can't be reconciled, that is a real spec
ambiguity for the PO — it is marked xfail on purpose.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

import pytest

# These imports will fail until the agent creates the module — expected.
from app.services.prediction import (
    AttemptPercentage,
    PredictionConfig,
    predict_performance,
)


def _attempts(percentages: list[float]) -> list[AttemptPercentage]:
    """Build attempts oldest→newest with increasing timestamps."""
    base = datetime(2026, 1, 1)
    return [
        AttemptPercentage(percentage=p, saved_at=base + timedelta(days=i))
        for i, p in enumerate(percentages)
    ]


def test_five_attempts_uses_full_weights():
    # Most recent is the LAST in oldest→newest order.
    # Percentages newest→oldest: 72, 88, 76, 84, 80
    result = predict_performance(_attempts([80, 84, 76, 88, 72]), PredictionConfig())
    expected = 72 * 0.35 + 88 * 0.25 + 76 * 0.20 + 84 * 0.12 + 80 * 0.08
    assert result.predicted_percentage == pytest.approx(round(expected, 2))
    assert result.confidence == "normal"


@pytest.mark.xfail(reason="BRD states 80.08% for this set but ordering convention is ambiguous — PO must confirm")
def test_brd_worked_example():
    result = predict_performance(_attempts([80, 84, 76, 88, 72]), PredictionConfig())
    assert result.predicted_percentage == pytest.approx(80.08)


def test_fewer_than_five_insufficient_by_default():
    result = predict_performance(_attempts([80, 84, 76, 88]), PredictionConfig())
    assert result.sufficient is False
    assert result.predicted_percentage is None


def test_fewer_than_five_with_limited_data_normalises_weights():
    cfg = PredictionConfig(allow_limited_data=True)
    result = predict_performance(_attempts([80, 84, 76, 88]), cfg)
    # 4 attempts: weights 0.35,0.25,0.20,0.12 renormalised to sum 1.0
    w = [0.35, 0.25, 0.20, 0.12]
    total = sum(w)
    norm = [x / total for x in w]
    # newest→oldest: 88, 76, 84, 80
    expected = 88 * norm[0] + 76 * norm[1] + 84 * norm[2] + 80 * norm[3]
    assert result.predicted_percentage == pytest.approx(round(expected, 2))
    assert result.confidence == "limited"


def test_never_zero_fills_missing_attempts():
    """A single 90% attempt with limited data must predict 90, not be
    diluted by zeros for the four missing slots."""
    cfg = PredictionConfig(allow_limited_data=True)
    result = predict_performance(_attempts([90]), cfg)
    assert result.predicted_percentage == pytest.approx(90.0)


def test_zero_attempts_empty_state():
    result = predict_performance([], PredictionConfig())
    assert result.sufficient is False
    assert result.predicted_percentage is None


def test_uses_only_five_most_recent():
    # 6 attempts; oldest (50) must be ignored.
    result = predict_performance(
        _attempts([50, 80, 84, 76, 88, 72]), PredictionConfig()
    )
    expected = 72 * 0.35 + 88 * 0.25 + 76 * 0.20 + 84 * 0.12 + 80 * 0.08
    assert result.predicted_percentage == pytest.approx(round(expected, 2))
