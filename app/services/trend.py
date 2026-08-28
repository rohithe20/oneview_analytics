from __future__ import annotations

from dataclasses import dataclass

MIN_ATTEMPTS_FOR_TREND = 4  # BRD §15
IMPROVING_THRESHOLD = 5.0
NEEDS_FOCUS_THRESHOLD = -5.0


@dataclass
class TrendResult:
    status: str
    delta: float | None


def classify_trend(percentages: list[float]) -> TrendResult:
    """Classify the direction of recent performance per BRD §15.

    `percentages` must be valid attempt percentages within one
    (student, level, subject) scope, ordered oldest -> newest.
    """
    if len(percentages) < MIN_ATTEMPTS_FOR_TREND:
        return TrendResult(status="More data needed", delta=None)

    latest_avg = sum(percentages[-2:]) / 2
    prev_avg = sum(percentages[-4:-2]) / 2
    delta = latest_avg - prev_avg

    if delta >= IMPROVING_THRESHOLD:
        status = "Improving"
    elif delta <= NEEDS_FOCUS_THRESHOLD:
        status = "Needs Focus"
    else:
        status = "Stable"

    return TrendResult(status=status, delta=delta)


__all__ = ["classify_trend", "TrendResult"]
