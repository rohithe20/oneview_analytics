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


__all__ = ["SubtopicStats", "PriorityArea", "rank_priorities"]
