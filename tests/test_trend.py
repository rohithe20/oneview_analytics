"""Tests for trend classification — BRD §15. Boundary behaviour at ±5pp
is the point of this suite.

Agent: implement app/services/trend.py per docs/specs/trend-logic.md to
make these pass.
"""
from __future__ import annotations

import pytest

from app.services.trend import classify_trend


def test_fewer_than_four_is_more_data_needed():
    assert classify_trend([70, 75, 80]).status == "More data needed"


def test_improving_above_threshold():
    # prev avg = (60+62)/2 = 61; latest avg = (70+72)/2 = 71; delta +10
    assert classify_trend([60, 62, 70, 72]).status == "Improving"


def test_needs_focus_below_threshold():
    # prev avg = 80; latest avg = 68; delta -12
    assert classify_trend([82, 78, 70, 66]).status == "Needs Focus"


def test_stable_within_band():
    # delta small
    assert classify_trend([70, 72, 73, 71]).status == "Stable"


def test_boundary_exactly_plus_five_is_improving():
    # prev avg = 70; latest avg = 75; delta exactly +5.0
    assert classify_trend([70, 70, 75, 75]).status == "Improving"


def test_boundary_exactly_minus_five_is_needs_focus():
    # prev avg = 75; latest avg = 70; delta exactly -5.0
    assert classify_trend([75, 75, 70, 70]).status == "Needs Focus"


def test_boundary_plus_four_ninety_nine_is_stable():
    # prev avg = 70; latest avg = 74.99; delta +4.99
    assert classify_trend([70, 70, 74.99, 74.99]).status == "Stable"


def test_zero_delta_is_stable():
    assert classify_trend([70, 70, 70, 70]).status == "Stable"


def test_uses_latest_four_when_more_present():
    # Only the last 4 matter: [_, 70,70,75,75] → Improving
    assert classify_trend([10, 70, 70, 75, 75]).status == "Improving"
