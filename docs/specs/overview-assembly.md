# Overview Assembly Service

Source: derived from overview-ui.md §4 and the five engine specs.
This is the SEAM between the engines and the Overview page. It calls the
engines; it never re-implements them.

## What it does

Given one scope `(student_id, exam_level, component_family)`, assemble a
single `FamilyOverview` object carrying every value the family panel
needs — so the template renders from one object and contains no logic.

## Function contract

    build_family_overview(
        db: Session,
        student_id: int,
        exam_level: str,       # 'AS' | 'A'
        component_family: str,  # 'Pure' | 'Statistics'
    ) -> FamilyOverview

The function:
1. Fetches scope-filtered attempt percentages (oldest→newest) and topic/
   subtopic aggregates via the data-access layer / analytics views.
2. Calls each engine with its required inputs.
3. Packs the results into `FamilyOverview`.

It does NOT query across scopes, and does NOT re-derive any engine's
logic. If an engine needs pre-aggregated inputs (priority needs
`SubtopicStats`), the assembly layer builds those inputs from the views
and hands them over.

## The FamilyOverview dataclass

    @dataclass
    class MetricSummary:
        average_percentage: float | None
        recent_percentage: float | None
        papers_completed: int
        target_value: int | None        # None when no target set
        completion_percentage: float | None  # None when target is 0/unset
        available_papers: int

    @dataclass
    class FamilyOverview:
        component_family: str
        exam_level: str

        # 4.1 Predicted Performance
        predicted_percentage: float | None
        prediction_confidence: str        # 'normal' | 'limited' | 'none'

        # 4.2 Metric row
        metrics: MetricSummary

        # 4.3 Trend
        trend_status: str                 # Improving/Stable/Needs Focus/More data needed
        trend_points: list[float]         # recent percentages for the chart

        # 4.4 Priority (up to 3)
        priorities: list[PriorityArea]    # from priority engine

        # 4.5 Insight
        insight_text: str | None
        insight_rule_id: str

        # 4.6 Recommendation
        recommendation_text: str | None
        recommendation_rule_id: str

        # cross-cutting
        has_sufficient_data: bool         # False → panel shows empty/insufficient state
        attempts_count: int

## Data sufficiency (drives the UI states)

`has_sufficient_data` is True when there are ≥5 completed valid attempts
in scope (the overall gate from the BRD). The template uses it to choose
between the populated view and the insufficient/empty state.

Individual engines ALSO return their own insufficient states (trend needs
4, priority needs 3 observations per subtopic). The panel respects both:
the family-level gate for the whole panel, and each engine's own state
for its component. Never fabricate a value to fill a gap.

## Engine wiring (what feeds what)

| Field | Engine | Input the assembly layer prepares |
|---|---|---|
| predicted_percentage | prediction | list[AttemptPercentage] oldest→newest |
| trend_status/points | trend | list[float] percentages oldest→newest |
| priorities | priority | list[SubtopicStats] from v_topic_performance + subtopic aggregates |
| insight | insight | SubjectContext: sufficiency, top priority, its trend, X/Y error counts, averages |
| recommendation | recommendation | the Insight result + same context |
| metrics | planning/metrics | scope-filtered attempt totals + study_target |

## Test contract (tests/test_overview_assembly.py)

- With a seeded student having ≥5 Pure AS attempts: returns a populated
  FamilyOverview; predicted_percentage is not None; priorities non-empty
  if a weak subtopic exists.
- With <5 attempts: has_sufficient_data is False; no fabricated numbers.
- Scope isolation: building for (Pure, AS) never includes Statistics or
  A-level attempts. Seed one attempt in another scope and assert it does
  not affect the result.
- The function calls engines, does not reimplement: a spot check that
  trend_status matches classify_trend on the same percentages.

## What NOT to do

- Do not put any classification or calculation logic here that belongs in
  an engine — this layer only orchestrates and packs.
- Do not read across levels or families.
- Do not fabricate values for insufficient states.
- Do not query inside the template — the template gets a finished
  FamilyOverview.
