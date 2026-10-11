from __future__ import annotations

from dataclasses import dataclass

MIN_OBSERVATIONS = 3  # BRD §19 rule 1
HIGH_GAP_THRESHOLD = 15.0
HIGH_REPEATED_ERROR_GAP_THRESHOLD = 10.0
MEDIUM_GAP_MIN = 5.0
MEDIUM_GAP_MAX = 14.0
MONITOR_GAP_MIN = 0.0
MONITOR_GAP_MAX = 4.0

PRIORITY_RANK = {"High": 0, "Medium": 1, "Monitor": 2}

MAX_PRIORITY_AREAS = 3


@dataclass
class SubtopicStats:
    topic: str
    subtopic: str
    subtopic_avg: float
    subject_avg: float
    observation_count: int
    repeated_error_signal: bool
    improving: bool
    recent_error_frequency: float


@dataclass
class PriorityArea:
    topic: str
    subtopic: str
    percentage: float
    priority: str
    gap: float


def _classify(stat: SubtopicStats) -> str | None:
    """Stage 1 — classify a single subtopic per BRD §19, rules 1-6, top to bottom."""
    if stat.observation_count < MIN_OBSERVATIONS:
        return None

    gap = stat.subject_avg - stat.subtopic_avg

    if gap >= HIGH_GAP_THRESHOLD:
        return "High"
    if gap >= HIGH_REPEATED_ERROR_GAP_THRESHOLD and stat.repeated_error_signal:
        return "High"
    if MEDIUM_GAP_MIN <= gap <= MEDIUM_GAP_MAX:
        return "Medium"
    if MONITOR_GAP_MIN <= gap <= MONITOR_GAP_MAX:
        return "Monitor"

    return None


STATUS_INSUFFICIENT = "Insufficient data"

# The Stage-1 priority level -> the Topic Analysis status vocabulary. Same
# thresholds, different label set: the priority pills read High/Medium/Monitor,
# the Topic Analysis tables read High Priority/Needs Focus/Monitor/Strong.
_PRIORITY_TO_STATUS = {"High": "High Priority", "Medium": "Needs Focus", "Monitor": "Monitor"}


def classify_status(stat: SubtopicStats) -> str:
    """Map one subtopic's classification to a Topic Analysis status label.

    Topic Analysis reuses the priority engine's gap thresholds rather than
    defining its own bands (docs/specs/topic-analysis-service.md "Reuse, don't
    reinvent"; BRD §8 — Overview and Topic Analysis share one rule). This is the
    threshold->label mapping both surfaces share: it runs the same `_classify`
    used by ranking, then names the result for the tables.

    - Below the observation minimum -> "Insufficient data", never a weakness
      label (§10).
    - At or above the benchmark (no priority) with enough data -> "Strong".

    Note: `_classify` returns None for a small band of gaps between the Monitor
    and Medium ranges (4 < gap < 5); those map to "Strong" here. That gap in the
    priority thresholds is inherited from the priority engine, not introduced —
    flagged for the PO rather than papered over with a new band.
    """
    if stat.observation_count < MIN_OBSERVATIONS:
        return STATUS_INSUFFICIENT
    priority = _classify(stat)
    if priority is None:
        return "Strong"
    return _PRIORITY_TO_STATUS[priority]


def rank_priorities(subtopics: list[SubtopicStats]) -> list[PriorityArea]:
    """Classify and rank subtopics into the top 3 priority areas per BRD §19-20.

    `subtopics` are pre-aggregated, scope-filtered stats — this function does
    not query, it only classifies and ranks.
    """
    classified: list[tuple[SubtopicStats, str, float]] = []
    for stat in subtopics:
        priority = _classify(stat)
        if priority is None:
            continue
        gap = stat.subject_avg - stat.subtopic_avg
        classified.append((stat, priority, gap))

    classified.sort(
        key=lambda item: (
            PRIORITY_RANK[item[1]],
            -item[2],
            -item[0].recent_error_frequency,
            -item[0].observation_count,
        )
    )

    return [
        PriorityArea(
            topic=stat.topic,
            subtopic=stat.subtopic,
            percentage=stat.subtopic_avg,
            priority=priority,
            gap=gap,
        )
        for stat, priority, gap in classified[:MAX_PRIORITY_AREAS]
    ]


__all__ = [
    "SubtopicStats",
    "PriorityArea",
    "rank_priorities",
    "classify_status",
    "STATUS_INSUFFICIENT",
]
