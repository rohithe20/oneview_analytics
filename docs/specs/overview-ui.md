# Overview Dashboard — UI Specification

The agent building the Overview page MUST match this. It is derived from
the approved BRD sample visuals and the OneView visual direction. Do not
invent a different layout, palette, or component style. When the BRD and
this file agree, that is the target; nothing here is optional styling.

Stack: Jinja2 templates + HTMX, Tailwind via CDN. No React, no build step.
Desktop/laptop target (the BRD states desktop MVP — do not build mobile
layouts).

---

## 1. Global shell (shared across all three MVP pages)

Every MVP page uses ONE shared layout: a fixed left sidebar + a global
header + a content area. Build this as `base.html`; Overview, Record and
Topic Analysis all extend it. Do NOT create a second nav or header.

### Left sidebar (fixed, ~240px)
- OneView wordmark/logo at top with the tagline line.
- Nav items, in order: **Overview**, **Record Practice Paper**,
  **Topic Analysis**. (Other items from the mockup — Past Papers,
  Progress, Reports — are POST-MVP; render them greyed/disabled or omit.
  Do not wire them.)
- The current page is highlighted with the purple accent (see palette).
- Student identity block pinned at the bottom: avatar circle with
  initials, student name, "AS Level Student" sub-label, a log-out row.

### Global header (top of content area)
- Page title on the left (e.g. "Overview").
- On the right: the **scope context** — student name, and the
  **Level selector (AS / A)**. This selector is global context AND drives
  the whole page (see §3).

---

## 2. Palette and visual treatment

Approved OneView direction — purple/blue primary. Use these Tailwind
tokens consistently:

| Role | Tailwind | Use |
|---|---|---|
| Primary accent | `violet-600` / `purple-600` | active nav, primary buttons, headings accent |
| Primary hover | `violet-700` | button hover |
| Surface | `white` on `slate-50` page bg | cards |
| Card border | `slate-200` | 1px borders, `rounded-xl` |
| Text primary | `slate-900` | headings, values |
| Text muted | `slate-500` | labels, sub-text |
| Strong (good) | `emerald-500` | ≥75% performance |
| Moderate | `amber-500` | 50–74% |
| Weak | `rose-500` | <50% |

- Cards: white, `rounded-xl`, `border border-slate-200`, `p-5`, subtle
  shadow (`shadow-sm`). Generous whitespace — the BRD says clear, not
  dense.
- Section headers: unnumbered, `slate-900` with the purple accent used
  sparingly. No numbered headings in the UI.
- Percentage/status colour ALWAYS follows the strong/moderate/weak bands
  above so colour is meaningful, never decorative.

---

## 3. The scope model (this governs everything)

The page always renders for a scope tuple:
`(student_id, exam_level, component_family)`.

- **Level (AS / A)** is chosen in the header. Switching it refreshes the
  ENTIRE page — every card, chart, priority, insight. AS and A data are
  never shown together.
- **Two component families — Pure and Statistics — are shown
  SIDE BY SIDE**, as two independent columns/panels. They are never
  combined into one score. Each family panel is fully self-contained:
  its own prediction, metrics, trend, priorities, insight,
  recommendation.

So the content area is two parallel columns (Pure | Statistics), each
containing the full stack of §4 components, under one shared Level
selector.

Implement the Level switch as an HTMX swap of the content area, or a
full navigation with a query param — either is fine; the whole page must
reflect the selected level with no stale data from the other level.

---

## 4. Components inside each family panel (top to bottom)

Order matters — it matches the BRD reading order.

### 4.1 Predicted Performance card
- Large predicted value, shown as **percentage primary** with a mark
  range as secondary (e.g. "78%" with "≈ 58–60 / 75").
- Label reads **"Predicted Performance"** — NEVER "Prediction V1".
- If limited-confidence: show a small "limited confidence" chip.
- Insufficient data: "More data needed" state, no number invented.

### 4.2 Metric row (small stat cards)
A row of compact cards:
- **Average %** (scope average)
- **Recent %** (latest attempt)
- **Papers Completed** vs **Target** with a completion bar
- If target = 0: "No target set" state, never a divide-by-zero.

### 4.3 Trend card
- Status pill: **Improving** (emerald), **Stable** (amber/slate),
  **Needs Focus** (rose), or **More data needed** (muted).
- A small line chart of recent attempt percentages (Chart.js, one
  instance per family). Chart shows available points even when
  classification is withheld (<4 attempts).

### 4.4 Priority Areas card
- Up to 3 rows. Each: topic → subtopic, the percentage, and a priority
  tag — **High** (rose), **Medium** (amber), **Monitor** (slate).
- Each row is CLICKABLE → routes to Topic Analysis for that
  topic/subtopic (OV-T-019). For now the link can point at a stub route.
- If none qualify or data insufficient: a "more data needed" empty state.

### 4.5 Insight card
- One sentence, from the approved insight templates only. No free text.
- Muted/neutral styling; it's informational.

### 4.6 Recommendation card
- One approved recommendation string mapped from the insight.
- Slightly emphasised (it's the "what to do") but not a button.

---

## 5. States (half the spec — do NOT skip)

Every component has three states; build all three:

- **Populated** — real values.
- **Insufficient data** — explicit, honest message; never a fabricated
  number or a false weakness. This is a BRD hard rule.
- **Empty** (no attempts yet in scope) — a gentle "record a paper to
  begin" prompt.

Loading states: if a panel fetches via HTMX, show a lightweight skeleton
or "Loading…" rather than a blank flash.

---

## 6. Layout skeleton (reference structure)

```
┌────────────────────────────────────────────────────────────┐
│ Sidebar │  Header:  Overview            [ AS ▾ ]  Student   │
│         ├──────────────────────────────────────────────────┤
│ Overview│  ┌─ Pure Mathematics ──┐  ┌─ Statistics ───────┐  │
│ Record  │  │ Predicted Perf.     │  │ Predicted Perf.    │  │
│ Topic   │  │ [avg][recent][compl]│  │ [avg][recent][comp]│  │
│         │  │ Trend + chart       │  │ Trend + chart      │  │
│         │  │ Priority (up to 3)  │  │ Priority (up to 3) │  │
│         │  │ Insight             │  │ Insight            │  │
│         │  │ Recommendation      │  │ Recommendation     │  │
│         │  └─────────────────────┘  └────────────────────┘  │
└────────────────────────────────────────────────────────────┘
```

Two equal columns on desktop. Each column is one family. The header's
Level selector governs both.

---

## 7. Non-negotiables (BRD §32 restated for UI)

- Label is "Predicted Performance", never the internal method name.
- Never mix AS and A. Never merge Pure and Statistics.
- Insufficient data is never shown as weakness.
- Colour bands are meaningful (strong/moderate/weak), not decorative.
- One shared shell; no alternate nav or header.
- Priority is displayed by its rule-based tag, never implied to be a
  pure marks-lost ranking.
- Every insight/recommendation shown is one of the approved strings.

---

## 8. What NOT to build (scope guard for the demo)

- No Past Papers / Progress / Reports pages (post-MVP nav — disabled).
- No settings, no profile editing.
- No mobile layout.
- No auth screen yet (hardcode student_id=1 for now; the scope filter
  already threads student_id so swapping to a session later is contained).
- No new analytics on this page beyond the six approved components.
