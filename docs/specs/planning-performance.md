# Planning & Performance Metrics

Source: BRD §7, §17, §18, §35. The non-engine numbers on the dashboard:
targets, completion, averages, recent score.

## New data entity: Practice Target

The BRD introduces a per-scope target. This needs a new table.

Scope note: the subject is always Maths (9709). The independence is per
COMPONENT FAMILY (Pure vs Statistics), not per subject. So the target is
keyed by component_family, not subject_id.

    study_targets
        id                PK
        student_id        FK -> students
        exam_level        'AS' | 'A'
        component_family  'Pure' | 'Statistics'
        target_value      int
        UNIQUE (student_id, exam_level, component_family)

One target per (student, level, component_family). Independent across
families and levels (§6, §35).

`component_family` is derived from a paper's `component` number via a
lookup (keep it as a small reference table or config dict). Available
Papers, Completed, and every metric below are counted within the
selected (level, component_family) scope.

## Planning metrics (§17)

| Metric | Rule |
|---|---|
| Available Papers | Count of eligible papers in the paper DB for (level, family). System-controlled. |
| Practice Target | Stored per (student, level, family). Integer ≥ 0, ≤ Available Papers (OV-PL-003). |
| Papers Completed | Count of DISTINCT papers with a valid saved attempt in (level, family). Re-attempting a paper does not increment it. |
| Remaining | max(Target − Completed, 0) (OV-PL-005). |
| Completion % | Completed ÷ Target × 100. **If Target = 0, show not-set state, never divide-by-zero** (OV-PL-006). |

Completion is measured against the **target**, not available papers
(§7). 18 completed of a target of 30 = 60%, even if 50 are available.

Changing a target never alters historical attempts or analytics
(OV-PL-007, §28).

## Performance metrics (§18)

Each metric below is computed over the COUNTED attempts — one per
distinct paper, the most recent (see "The counted attempt" below).

| Metric | Rule |
|---|---|
| Average Score | Arithmetic mean of the counted attempt scores in scope. |
| Average Percentage | Arithmetic mean of the counted attempt percentages in scope. Independent of target. |
| Recent Score | Latest counted attempt in scope (latest timestamp wins). |
| Recent Percentage | Percentage of the same attempt as Recent Score. |

## The counted attempt (PO decision, 2026-09-05)

**For each distinct paper, only the MOST RECENT completed attempt
counts.** A paper attempted twice contributes ONE value — the latest — to
every metric and every engine. An earlier attempt at the same paper is
superseded, not averaged in: re-sitting a paper replaces that paper's
result rather than adding a second observation.

This supersedes the earlier, narrower decision that made only
`Papers Completed` distinct-paper based. It applies consistently, with no
exceptions:

- `Papers Completed` — count of distinct `paper_id` in scope. Six
  attempts on one paper is one paper completed. `Completion %` and
  `Remaining` derive from that count, so completion can never exceed
  100% by re-attempting.
- Average Score / Average Percentage — mean over the counted attempts.
- Recent Score / Recent Percentage — the latest counted attempt.
- Trend (`trend_points`) and Prediction — the counted series,
  oldest→newest.
- Priority — a subtopic's `observation_count` counts distinct papers, so
  re-sitting one paper cannot carry a subtopic over the engine's
  3-observation gate. Its repeated-error window (X of the last Y) counts
  distinct papers too.
- The `>=5` family sufficient-data gate and every per-engine gate —
  counted in counted attempts, i.e. distinct papers.

Consequently `attempts_count` and `papers_completed` are the same number.

### Where the rule lives

The reduction is implemented ONCE, in the data-access layer, so no engine
re-derives it:

- `v_latest_paper_attempts` (migration `7f3c9d2b41ae`) selects the newest
  completed attempt per `(student_id, paper_id)`, breaking a
  `completed_at` tie on `id` so the choice is deterministic.
- `v_topic_performance` is defined on top of it, so every topic/subtopic
  aggregate inherits the reduction.
- `v_attempt_totals` deliberately stays the raw per-attempt view — it is
  the fact view. Readers reduce it by joining `v_latest_paper_attempts`,
  which is what `app/services/overview.py` does.

Superseded attempts are never deleted. They stay in `attempts` as
history; they simply do not feed analytics — which is also what keeps
§32 rule 7 true: correcting a paper never creates a duplicate attempt.

## Function contracts

    get_planning_metrics(db, student_id, level, component_family) -> PlanningMetrics
    get_performance_metrics(db, student_id, level, component_family) -> PerformanceMetrics
    set_target(db, student_id, level, component_family, value) -> StudyTarget

`set_target` validates 0 ≤ value ≤ available_papers, raising on
violation (OV-PL-003).

## Test cases (QA matrix)

- OV-T-003: target 30, completed 18 → 60%; available count does not
  affect the formula.
- OV-T-003b: 3 attempts spread over 2 distinct papers → Papers Completed
  = 2, and attempts_count / averages / trend see 2 values, not 3.
- OV-T-003c: a paper attempted twice contributes only its latest result —
  in both directions, whether the re-sit is better or worse.
- OV-T-004: target 0 → not-set state, no divide-by-zero.
- OV-T-005: average score and percentage match a known dataset.
- OV-T-006: recent score = most recent counted attempt.

## What NOT to do

- Do not divide by zero when target is 0.
- Do not let available-papers count enter the completion formula.
- Do not let a target change touch historical attempts.
- Do not mix levels or families.
- Do not average a paper's attempts together, and do not let a re-sit add
  an observation to any count or gate.
- Do not re-implement the reduction in an engine, a route or a template —
  join `v_latest_paper_attempts` in the data-access layer instead.