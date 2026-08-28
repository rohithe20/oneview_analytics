from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

FULL_WEIGHTS: tuple[float, ...] = (0.35, 0.25, 0.20, 0.12, 0.08)  # BRD §16


@dataclass
class AttemptPercentage:
    percentage: float
    saved_at: datetime


@dataclass
class PredictionConfig:
    allow_limited_data: bool = False
    weights: tuple[float, ...] = FULL_WEIGHTS
    round_digits: int = 2


@dataclass
class PredictionResult:
    predicted_percentage: float | None
    confidence: str
    sufficient: bool


def predict_performance(
    attempts: list[AttemptPercentage], config: PredictionConfig
) -> PredictionResult:
    """Predict a student's next performance per BRD §16.

    `attempts` must be valid attempt percentages within one
    (student, exam_level, component_family) scope, ordered oldest -> newest.
    """
    if not attempts:
        return PredictionResult(
            predicted_percentage=None, confidence="insufficient", sufficient=False
        )

    n_full = len(config.weights)

    if len(attempts) >= n_full:
        recent = attempts[-n_full:]
        weights = config.weights
        confidence = "normal"
    elif config.allow_limited_data:
        recent = attempts
        raw_weights = config.weights[: len(attempts)]
        total = sum(raw_weights)
        weights = tuple(w / total for w in raw_weights)
        confidence = "limited"
    else:
        return PredictionResult(
            predicted_percentage=None, confidence="insufficient", sufficient=False
        )

    newest_first = list(reversed(recent))
    weighted_sum = sum(a.percentage * w for a, w in zip(newest_first, weights, strict=True))

    return PredictionResult(
        predicted_percentage=round(weighted_sum, config.round_digits),
        confidence=confidence,
        sufficient=True,
    )


__all__ = ["AttemptPercentage", "PredictionConfig", "PredictionResult", "predict_performance"]
