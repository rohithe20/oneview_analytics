# Record Practice Paper — Write-Path Service

Source: Record Practice Paper BRD+FSD MVP v1.0 (§7-16). This spec covers
the BACKEND service and validation only. The page/UI is a separate spec.
No engines, no analytics — this is data capture.

## What it does

Records a completed practice-paper attempt: takes marks-lost per
sub-part + an error type per sub-part, validates, and persists as ONE
attempt (create) or updates an existing attempt (edit). Feeds the same
`attempts` / `sub_part_results` tables the analytics already read.

## THE CRITICAL CONVERSION (read first)

The student enters **MARKS LOST** per sub-part. The schema stores
**marks_scored** (`sub_part_results.marks_scored`). So:

    marks_scored = max_marks - marks_lost

The service converts on the way in. NEVER store marks_lost as
marks_scored. Every existing analytic reads marks_scored, so getting
this backwards inverts every downstream number. This is the single most
important line in the spec.

## Schema note — error_type already exists

`sub_part_results.error_type` was added in an earlier migration
(nullable String). This service populates it. No new migration needed
for results. Confirm `attempts` has `date_completed` — if the BRD's
"Date Completed" isn't on the model yet, add it (nullable date) in a
small migration.

## Function contracts (app/services/record.py)

    @dataclass
    class SubPartEntry:
        sub_part_id: int
        marks_lost: int
        error_type: str          # one of the 9 controlled values

    @dataclass
    class RecordResult:
        attempt_id: int
        total_marks: int         # 75 for MVP
        total_marks_lost: int
        total_score: int
        percentage: float

    def save_attempt(
        db, student_id, paper_id, date_completed,
        entries: list[SubPartEntry],
        attempt_id: int | None = None,   # None = create, set = update
    ) -> RecordResult

`attempt_id is None` → create exactly one new attempt (RP-F-001).
`attempt_id` set → update THAT attempt in place (RP-F-005/006), never
create a duplicate.

## The nine Error Types (controlled)

    No Error, Conceptual Error, Calculation Error, Careless Error,
    Application Error, Misread Question, Incomplete Answer,
    Time Pressure, Forgot Formula / Rule

Keep these as an enum or a config list (Maintainability NFR — data
driven, not scattered string literals).

## Error-type rules (§8, RP-V-008/009)

- marks_lost == 0  → error_type MUST be "No Error". Reject anything else.
- marks_lost > 0   → error_type MUST be one of the 8 non-No-Error values.
  Reject "No Error" (RP-V-009) and reject blank.

The UI locks the dropdown, but the SERVICE must enforce it too — a UI
lock is not validation.

## Validation rules (§12) — all enforced in the service

| ID | Rule | Behaviour |
|---|---|---|
| RP-V-001 | Required paper fields missing (level/paper/session/variant/date) | reject, clear message |
| RP-V-004 | Marks Lost blank on any row | reject |
| RP-V-005 | Marks Lost < 0 | reject |
| RP-V-006 | Marks Lost > that row's Max Marks | reject |
| RP-V-007 | Marks Lost non-integer | reject (whole numbers only) |
| RP-V-008 | Marks Lost = 0 with an error category | force No Error (or reject) |
| RP-V-009 | Marks Lost > 0 with No Error | reject |
| RP-V-010 | Total Marks Lost > 75 | reject |
| RP-V-011 | Duplicate submit of same new form | idempotency — see below |
| RP-V-012 | Editing existing attempt | update, never duplicate |

Collect all violations and return them together (like the seed loader),
so the UI can show every bad row at once — don't fail on the first.

## Calculations (§14) — all derived, never stored as entered

    total_marks       = 75 (MVP fixed; ideally SUM(max_marks) as a check)
    total_marks_lost  = sum(entry.marks_lost)
    total_score       = total_marks - total_marks_lost
    percentage        = total_score / total_marks * 100

Percentage is computed, never accepted from the client (§14 rule 14).

## Create vs update (§11, §16) — the key behaviour

- Create: new `attempts` row (status COMPLETED), one `sub_part_results`
  row per entry with converted marks_scored + error_type.
- Update: find the attempt by attempt_id, verify it belongs to this
  student (Security NFR — §19), UPSERT each sub_part_result
  (the UNIQUE(attempt_id, sub_part_id) constraint makes this clean),
  update date_completed, bump updated_at. Do NOT insert a new attempt.
  The completed-attempt COUNT must not increase (RP-F-006, RP-T-015).

## Idempotency (RP-V-011)

Prevent an accidental double-submit of the SAME new form creating two
attempts. The UNIQUE(attempt_id, sub_part_id) already prevents duplicate
rows within an attempt; for the attempt itself, the UI should disable the
button on submit AND the service can accept an idempotency key or check
for an identical just-created attempt. For MVP, a submit-token or
button-disable is acceptable — flag the approach chosen.

## Downstream (RP-F-007)

Because analytics are computed on read (views + engines, nothing
cached), a saved/updated attempt is automatically reflected next time
Overview/Topic Analysis query. No explicit "recalculate" step needed —
note this in the response so the caller knows analytics are live.

## Test contract (tests/test_record.py)

- RP-T-011: entries summing to 7 marks lost → score 68/75, 90.7%.
- Conversion: a sub-part with max 5, marks_lost 2 → stored marks_scored 3.
- RP-V-006: marks_lost > max_marks rejected.
- RP-V-009: marks_lost > 0 + No Error rejected.
- RP-V-008: marks_lost 0 + error category rejected/forced.
- RP-V-010: total lost > 75 rejected.
- Create makes exactly one attempt (RP-F-001).
- Update edits in place, attempt count unchanged (RP-F-006).
- Update verifies student ownership (security).
- All violations returned together, not first-only.

## What NOT to do

- Do NOT store marks_lost as marks_scored — convert.
- Do NOT accept a client-supplied total or percentage — derive.
- Do NOT create a second attempt on edit.
- Do NOT put any insight/recommendation/prediction logic here (§16, §18).
- Do NOT rely on the UI lock for validation — enforce in the service.