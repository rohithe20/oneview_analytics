# Topic Analysis — Page / UI

Source: Topic Analysis BRD+FSD MVP v1.0 (§4, §5, §13; FSD §2, §3, §8, §9).
Read-only diagnostic drill-down. Extends the shared shell. Renders the
`TopicAnalysisView` from `app/services/topic_analysis.py` — no logic in
the template.

## Shell & header (§4, FSD §3)

- Same `base.html` shell; left nav with Topic Analysis HIGHLIGHTED.
- Global header: student name, exam-level selector (AS/A), subject/family
  selector (Pure/Statistics), last-updated timestamp.
- Route protected via `CurrentStudent` (student_id from session).
- Match the Overview colour template exactly. No alternate nav/header.

## Layout (§5)

Single workspace, top to bottom:
1. Page title "Topic Analysis" + static subtitle ("See how you are
   performing across topics and subtopics based on all your recorded
   practice papers.").
2. Family header card ("Pure Mathematics" — do NOT append "Summary").
3. Five summary tiles: Papers Attempted (N of M available), Questions
   Analysed, Average Performance, Strongest Topic, Priority Topic.
4. Two tables side by side:
   - LEFT: Topic Performance (8 topics)
   - RIGHT: Subtopic Analysis (subtopics of the selected topic)
5. BELOW: Question-level lost-mark panel (for the selected subtopic).
6. A review tip: "Look up these questions in your original practice
   papers to review and practise them again."

## Topic Performance table (§6)

Columns: Topic | Questions | Average Score | Marks Lost | Status.
- All 8 Pure topics, syllabus order.
- Status badge coloured: Strong (emerald), Monitor (amber/slate),
  Needs Focus (deeper amber/orange), High Priority (rose).
- The selected topic row is highlighted.
- Clicking a row selects that topic → refreshes the Subtopic table and
  (via re-defaulting) the question panel. HTMX swap, or a link carrying
  selected_topic_id.
- Default selected = priority topic (Integration in the prototype).

## Subtopic Analysis table (§7)

Columns: Subtopic | Questions | Average Score | Marks Lost | Status.
- Subtopics of the selected topic (from the seeded taxonomy).
- Same status colour treatment.
- Default-selected = weakest eligible subtopic (lowest avg, ≥3 obs).
- Clicking a subtopic row → refreshes the question panel below.
- Heading reflects the selected topic (e.g. "Integration — Subtopic
  Analysis").

## Question-level lost-mark panel (§8, FSD §9)

Columns IN THIS ORDER: Year | Variant | Question | Your Score | Max Marks
| Marks Lost.
- Only questions with Marks Lost > 0.
- Sorted by Marks Lost DESCENDING.
- Variant shown as numeric combined code (11, 12, 13) — NO prefix label.
- Larger marks-lost values get visual emphasis (consistent with status
  colour treatment).
- NO dropdown/sort indicator beside the Marks Lost header.
- NO question text. NO "Review"/"open question" button (§12 data honesty).
- Empty state if the subtopic has no lost-mark records.

## Interaction (FSD §8)

| Action | Result |
|---|---|
| Click a topic row | that topic selected; its subtopics replace the panel; weakest subtopic re-defaults; question panel refreshes |
| Click a subtopic row | question panel refreshes for that subtopic |
| Change AS/A level | whole page reloads for that level only |
| Change Pure/Statistics | whole page reloads for that family only |

NO "Back to Topics" or "Back to Subtopics" links (§4, §13). Drill-down is
row-selection only.

## States (§10, FSD §10)

- Below 5 completed papers: reliability-dependent statuses show
  "Insufficient data" rather than Strong/Monitor/etc. Basic facts
  (papers attempted, average) still show.
- Subtopic with <3 observations: "Insufficient data" status.
- Selected subtopic with no lost-mark questions: empty state message,
  no fabricated rows.
- Statistics family with insufficient data: the whole analysis shows the
  insufficient state (consistent with Overview).

## Visual acceptance (§13) — check these exactly

- "Pure Mathematics" heading WITHOUT the word "Summary".
- No "Back to Topics" / "Back to Subtopics" links.
- No "across N questions" text.
- No dropdown indicator beside Marks Lost.
- Variants display as 11, 12, 13 (numeric, no prefix).
- In the sample state, Integration selected, Definite & Indefinite
  integration selected by default (weakest at its sample avg).
- Question table sorted by marks lost descending.
- The review tip points to the original practice papers.

## What NOT to do

- No prediction, insight, recommendation, or trend (this is the
  diagnostic screen, not Overview).
- No question text or paper-opening controls.
- No back-navigation links; no charts beyond the tables.
- No new nav/header; reuse the shell.
- No cross-scope data.
