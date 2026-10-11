# Topic Analysis — Service Layer

Source: Topic Analysis BRD+FSD MVP v1.0. This spec covers the BACKEND
data service. The page is a separate spec. Topic Analysis is READ-ONLY
and reuses Overview's data and calculation definitions — it introduces
NO new formulas (BRD §1, §12, FSD §6).

## What it does

Assembles, for one scope `(student_id, exam_level, component_family)`,
everything the Topic Analysis page displays:
- 5 summary tiles
- topic performance rows (all 8 Pure topics)
- subtopic performance rows for a selected topic
- question-level lost-mark records for a selected subtopic

## The scope invariant (same as everywhere)

Every query filters on `(student_id, exam_level, component_family)`.
AS/A never mix; Pure/Statistics never combine. The prototype scope is
AS + Pure Mathematics.

## Reuse, don't reinvent (§12, FSD §6)

Topic-level performance already exists in `v_topic_performance`.
Status classification (Strong/Monitor/Needs Focus/High Priority) uses
the SAME thresholds as Overview's priority engine. Do not define new
status bands here — call/reuse the existing rule. If the existing rule
lives in the priority engine, factor the threshold→label mapping into a
shared helper both use, rather than duplicating it.

## Status labels (BRD §6, §7)

Topics and subtopics carry a status: Strong, Monitor, Needs Focus,
High Priority. These map from the same performance/gap rules Overview
uses. Insufficient data → "Insufficient data", never a weakness label
(§10).

## Function contracts (app/services/topic_analysis.py)

    @dataclass
    class TopicRow:
        topic_id: int
        topic_name: str
        questions: int          # count of question outcomes for this topic
        average_score: float    # percentage
        marks_lost: int
        status: str             # Strong/Monitor/Needs Focus/High Priority/Insufficient data

    @dataclass
    class SubtopicRow:
        subtopic_id: int
        subtopic_name: str
        questions: int
        average_score: float
        marks_lost: int
        status: str

    @dataclass
    class LostMarkQuestion:
        year: int
        variant_display: str    # combined code e.g. "12" (see variant rule)
        question: str           # e.g. "6(b)"
        your_score: int
        max_marks: int
        marks_lost: int

    @dataclass
    class TopicAnalysisSummary:
        papers_attempted: int         # "18 of 28 available" — attempted + available
        papers_available: int
        questions_analysed: int
        average_performance: float
        strongest_topic_name: str
        strongest_topic_pct: float
        priority_topic_name: str
        priority_topic_pct: float

    @dataclass
    class TopicAnalysisView:
        summary: TopicAnalysisSummary
        topics: list[TopicRow]                 # all 8, sorted by syllabus order
        selected_topic_id: int                 # default = priority topic
        subtopics: list[SubtopicRow]           # for selected topic
        selected_subtopic_id: int | None       # default = weakest eligible
        lost_mark_questions: list[LostMarkQuestion]  # for selected subtopic

    def build_topic_analysis(
        db, student_id, exam_level, component_family,
        selected_topic_id: int | None = None,
        selected_subtopic_id: int | None = None,
    ) -> TopicAnalysisView

`selected_topic_id=None` → default to the priority topic (§7 default
selection). `selected_subtopic_id=None` → default to the weakest
eligible subtopic of the selected topic.

## Summary tiles (FSD §6, §11)

| Tile | Definition |
|---|---|
| Papers Attempted | distinct papers attempted in scope, shown as "N of M available" (M = seeded eligible papers in scope) |
| Questions Analysed | count of question outcomes in scope |
| Average Performance | average percentage in scope — SAME definition as Overview |
| Strongest Topic | highest-performing topic + its % |
| Priority Topic | topic chosen by the configured priority rules (NOT simply highest marks lost) + its % |

Papers Attempted uses distinct papers (consistent with the PO decision
that completion counts unique papers). Average Performance and all
percentages use the most-recent-attempt-per-distinct-paper data, same as
Overview.

## Default selection logic (§7, FSD §7)

1. Determine the priority topic from the configured priority rules
   (the same priority engine Overview uses). This is the default
   selected topic.
2. Load all subtopics of the selected topic (from the seeded taxonomy —
   parent_id relationships).
3. Among subtopics with sufficient data (≥3 relevant observations),
   select the one with the LOWEST average score as default.
4. Load lost-mark questions for the selected subtopic.
5. If the user passes a selected_topic_id, use it and re-default the
   subtopic to that topic's weakest eligible.
6. If the user passes a selected_subtopic_id, use it for the question list.

## Question-level lost-mark records (§8, FSD §9)

The one genuinely new query. For the selected subtopic, in scope:
- Join sub_part_results → sub_parts → questions → papers, filtered to
  the subtopic and to the student's most-recent attempt per paper.
- Include only rows where marks_lost > 0 (marks_lost = max_marks -
  marks_scored).
- Columns: Year, Variant (combined-code display), Question label,
  Your Score (marks_scored), Max Marks, Marks Lost.
- Sort by Marks Lost DESCENDING.
- Do NOT include the question text (OneView doesn't store papers).

## Variant display (open item — resolve here)

The BRD shows variants as "11, 12, 13" (combined component+variant
codes). This schema splits component and variant. Compose the display
as `component * 10 + variant` → e.g. component 1, variant 2 → "12".
Provide this as a small shared helper (Record's table needs it too).
Confirm the format with a test against the BRD's examples.

## Data sufficiency (§10, FSD §10)

- Overall reliability analytics need ≥5 completed papers (same as
  Overview's gate).
- Subtopic weakness classification needs ≥3 relevant observations;
  below that → "Insufficient data", not a weakness label.
- Basic facts (papers attempted, average) may show before the overall
  threshold.
- If a selected subtopic has no lost-mark questions, the question panel
  shows an empty state ("no marks lost in the available records"), not a
  fabricated row.

## Test contract (tests/test_topic_analysis.py)

- 8 topics returned, syllabus-ordered, for AS Pure.
- Priority topic is the default selected topic.
- Weakest eligible subtopic is default-selected (lowest avg with ≥3 obs).
- Question list contains only marks_lost > 0 rows, sorted desc.
- Variant display composes correctly (component 1, variant 2 → "12").
- Scope isolation: A-level / Statistics attempts don't leak into an
  AS Pure view.
- Subtopic with <3 observations → "Insufficient data" status.
- Average Performance matches Overview's value for the same scope
  (one source of truth).

## What NOT to do

- No new formulas — reuse Overview's calculations and status rules.
- No prediction/insight/recommendation/trend on this screen.
- No question text, no "open paper" action (data honesty §12).
- No cross-scope leaks.
- Do not fabricate question rows or paper identifiers.
