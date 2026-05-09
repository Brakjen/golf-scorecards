# Round Tracking & Insights — Implementation Plan

## Overview

Extend the existing scorecard generator into a personal round-tracking tool.
The workflow is:

1. Generate and print a scorecard (existing feature).
2. Play and record metrics on paper.
3. Transcribe the card into the web app via a spreadsheet-style entry form.
4. View round history, computed stats, and LLM-generated coaching insights.

Everything stays Python (FastAPI + Jinja2 + SQLite). No JS framework.

## Code Conventions

- All Python docstrings use **Google style** with `Args:`, `Returns:`, `Raises:`,
  and `Attributes:` sections as appropriate.
- All function arguments and return types must be annotated in the docstring.
- Exceptions raised must be documented in a `Raises:` section.
- Include additional documentation about non-obvious logic when necessary.

---

## Architecture

```
Existing:  Catalog ──→ Scorecard Builder ──→ PDF Export (print & play)

New:       Round Entry UI ──→ Round Service ──→ SQLite DB
                                    │
                                    ├──→ Stats Service (deterministic)
                                    │       • aggregates, trends, charts
                                    │       • handicap-relative analysis
                                    │
                                    └──→ Insights Service (OpenAI)
                                            • chat completion (GPT-4o)
                                            • 3-5 coaching insights per batch
                                            • cached until next round
```

---

## New Module Structure

```
src/golf_scorecards/
├── db/                        # NEW — database setup
│   ├── __init__.py
│   ├── connection.py          #   SQLite connection lifecycle
│   └── schema.sql             #   CREATE TABLE statements
├── rounds/                    # NEW — round persistence & stats
│   ├── __init__.py
│   ├── models.py              #   Round, RoundHole, RoundSummary
│   ├── repository.py          #   SQLite CRUD
│   ├── service.py             #   create, save, list, get, delete
│   └── stats.py               #   aggregated stats & handicap-relative analysis
├── insights/                  # NEW — LLM coaching insights
│   ├── __init__.py
│   ├── service.py             #   OpenAI chat completion + cache
│   ├── prompts.py             #   system instructions & query templates
│   └── serializers.py         #   round data → structured LLM context
├── templates/
│   ├── home.html              # EDIT — new landing page with cards + insights
│   ├── round_create.html      # NEW  — pick course/tee to start a round
│   ├── round_entry.html       # NEW  — spreadsheet-style 18-hole input grid
│   ├── round_detail.html      # NEW  — view a saved round with filled data
│   └── round_list.html        # NEW  — history of all rounds
├── web/
│   ├── dependencies.py        # EDIT — add round/stats/insights service deps
│   └── routes.py              # EDIT — add round + insights routes
├── config.py                  # EDIT — add db_path, openai_api_key settings
└── main.py                    # EDIT — add DB init on startup
```

---

## Data Model

### `rounds` table

| Column             | Type    | Notes                                    |
|--------------------|---------|------------------------------------------|
| id                 | TEXT    | UUID primary key                         |
| course_slug        | TEXT    | FK to catalog course                     |
| tee_name           | TEXT    | Selected tee                             |
| player_name        | TEXT    | Nullable                                 |
| round_date         | TEXT    | ISO date                                 |
| handicap_index     | REAL    | Nullable                                 |
| handicap_profile   | TEXT    | "men" or "women"                         |
| playing_handicap   | INTEGER | Computed WHS playing handicap            |
| course_rating      | REAL    | Snapshot from catalog at round creation   |
| slope_rating       | INTEGER | Snapshot from catalog at round creation   |
| scoring_mode       | TEXT    | "stroke" or "stableford"                 |
| target_score       | INTEGER | Nullable (stroke play only)              |
| course_snapshot    | TEXT    | JSON blob of course/tee data at creation |
| created_at         | TEXT    | ISO timestamp                            |
| updated_at         | TEXT    | ISO timestamp                            |

### `round_holes` table

| Column             | Type    | Notes                                    |
|--------------------|---------|------------------------------------------|
| id                 | TEXT    | UUID primary key                         |
| round_id           | TEXT    | FK to rounds.id                          |
| hole_number        | INTEGER | 1–18                                     |
| par                | INTEGER | From course snapshot                     |
| distance           | INTEGER | From course snapshot                     |
| handicap           | INTEGER | Hole handicap index from snapshot        |
| score              | INTEGER | Nullable (not yet entered)               |
| putts              | INTEGER | Nullable                                 |
| fir                | INTEGER | 0/1/NULL — fairway in regulation         |
| gir                | INTEGER | 0/1/NULL — green in regulation           |
| penalty_strokes    | INTEGER | Nullable                                 |
| miss_direction     | TEXT    | "left"/"right"/"short"/"long"/NULL       |
| up_and_down        | INTEGER | 0/1/NULL                                 |
| sand_save          | INTEGER | 0/1/NULL                                 |
| sz_in_reg          | INTEGER | 0/1/NULL — scoring zone in regulation    |
| down_in_3          | INTEGER | 0/1/NULL                                 |
| putt_under_4ft     | INTEGER | 0/1/NULL — made putt ≤4ft                |
| made_over_4ft      | INTEGER | 0/1/NULL — made putt >4ft                |
| notes              | TEXT    | Free text per hole                       |

### `insights_cache` table

| Column             | Type    | Notes                                    |
|--------------------|---------|------------------------------------------|
| id                 | TEXT    | UUID primary key                         |
| generated_at       | TEXT    | ISO timestamp                            |
| rounds_hash        | TEXT    | Hash of round IDs used for generation    |
| insights_json      | TEXT    | JSON array of 3-5 insight strings        |

---

## Routes

### Round CRUD

| Method | Path                          | Purpose                        |
|--------|-------------------------------|--------------------------------|
| GET    | `/rounds/new`                 | Round creation form            |
| POST   | `/rounds`                     | Create round, redirect to entry|
| GET    | `/rounds/{id}/edit`           | Spreadsheet entry form         |
| POST   | `/rounds/{id}`                | Save hole data                 |
| GET    | `/rounds/{id}`                | View saved round detail        |
| GET    | `/rounds`                     | Round history list             |
| POST   | `/rounds/{id}/delete`         | Delete a round                 |

### Insights

| Method | Path                          | Purpose                        |
|--------|-------------------------------|--------------------------------|
| POST   | `/insights/refresh`           | Regenerate cached insights     |

### Existing (unchanged)

| Method | Path                          | Purpose                        |
|--------|-------------------------------|--------------------------------|
| GET    | `/`                           | Landing page (updated layout)  |
| POST   | `/scorecards/preview`         | Scorecard browser preview      |
| POST   | `/scorecards/export/pdf`      | Scorecard PDF download         |

---

## Landing Page Layout

```
┌──────────────────────────────────────────────────────────┐
│  Golf Scorecards                                         │
│                                                          │
│  ┌──────────────────┐  ┌──────────────────┐             │
│  │  📋 Generate      │  │  ✏️ Enter         │             │
│  │  Scorecard        │  │  Round            │             │
│  │                   │  │                   │             │
│  │  Pick course &    │  │  Transcribe your  │             │
│  │  tee, download    │  │  paper scorecard  │             │
│  │  PDF to print     │  │  into the app     │             │
│  └──────────────────┘  └──────────────────┘             │
│                                                          │
│  ── Quick Stats (last 5 rounds) ───────────────────────  │
│  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐           │
│  │ Avg    │ │ GIR    │ │ FIR    │ │ Putts  │           │
│  │ Score  │ │        │ │        │ │ /round │           │
│  │  84.2  │ │ 38.9%  │ │ 57.1%  │ │  32.4  │           │
│  │ vs HCP │ │  ↑ +5% │ │  → 0%  │ │  ↑-1.2 │           │
│  │  -5.8  │ │        │ │        │ │        │           │
│  └────────┘ └────────┘ └────────┘ └────────┘           │
│                                                          │
│  ── Coach's Insights ─────────────── 1/4 ── ◄ ► ──────  │
│  "Your GIR% has improved from 28% to 39% over your      │
│  last 8 rounds. However, putts per GIR has regressed     │
│  to 2.1 — costing ~2 strokes/round vs your handicap.    │
│  Priority: lag putting from 20-40ft."                    │
│                                              Refresh ↻   │
│                                                          │
│  ── Recent Rounds ─────────────────────────────────────  │
│  Apr 20  Forus (58)       82  32 putts  GIR 44%         │
│  Apr 13  Solastranden     87  35 putts  GIR 33%         │
│  Apr 06  Forus (63)       85  30 putts  GIR 39%         │
│                                          See all →       │
└──────────────────────────────────────────────────────────┘
```

Sections only render when round data exists.

---

## Round Entry UI

Spreadsheet-style grid mirroring the printed scorecard:

```
┌─ Enter Round: Forus (58) — Apr 20, 2026 ────────────────┐
│                                                          │
│  Hole  Par  HCP  Score  Putts  FIR  GIR  Pen  Miss  U&D │
│  ───── ──── ──── ────── ────── ──── ──── ──── ───── ─── │
│   1     4    6   [   ]  [  ]   [○]  [○]  [ ]  [▼ ]  [○] │
│   2     5    2   [   ]  [  ]   [○]  [○]  [ ]  [▼ ]  [○] │
│   3     3   14   [   ]  [  ]   [ ]  [○]  [ ]  [▼ ]  [○] │
│   ...                                                    │
│   9     4   10   [   ]  [  ]   [○]  [○]  [ ]  [▼ ]  [○] │
│  ─── TURN ───────────────────────────────────────────── │
│  10    4    5   [   ]  [  ]   [○]  [○]  [ ]  [▼ ]  [○] │
│   ...                                                    │
│  18    4   12   [   ]  [  ]   [○]  [○]  [ ]  [▼ ]  [○] │
│                                                          │
│  Totals: Score: 82  Putts: 32  FIR: 8/14  GIR: 7/18    │
│                                                          │
│                              [Save Round]                │
└──────────────────────────────────────────────────────────┘
```

- Score and putts: number inputs.
- FIR, GIR, U&D, sand save: toggle checkboxes.
- Miss direction: small dropdown (left/right/short/long).
- Penalty: number input (default 0).
- Par, HCP, distance: pre-filled from course snapshot (read-only).
- Totals auto-computed with inline JS as you type.
- Tab order flows left-to-right, top-to-bottom.
- FIR column hidden for par 3s.

---

## Stats Service (Deterministic)

Pure Python computed from `round_holes` data. No LLM.

### Aggregate functions

- `avg_score(last_n)` — mean gross score
- `gir_percentage(last_n)` — greens in regulation %
- `fir_percentage(last_n)` — fairways in regulation %
- `avg_putts(last_n)` — mean putts per round
- `putts_per_gir(last_n)` — mean putts on GIR holes
- `up_and_down_percentage(last_n)` — scrambling %
- `three_putt_rate(last_n)` — % of holes with ≥3 putts
- `penalty_strokes_per_round(last_n)` — mean penalties
- `scoring_zone_conversion(last_n)` — SZ in reg → down in 3

### Handicap-relative analysis

Uses course rating + playing handicap as baseline:

```
Expected score = Course Rating + Playing Handicap
Differential   = Actual Score − Expected Score
```

Per-round and rolling average differential.

### Trend calculation

Compare last N rounds vs previous N rounds. Direction: improving / stable / declining.

### Simplified strokes-lost breakdown

```
SL_putting    = Total putts on GIR holes − (2 × GIR count)
SL_short_game = Missed GIR count − Up-and-down makes
SL_penalties  = Total penalty strokes
SL_approach   = derived from GIR miss rate relative to baseline
```

---

## Insights Service (OpenAI)

### Setup

- Single chat completion call per generation (no Assistants API).
- System prompt with golf coaching instructions baked into `prompts.py`.
- `openai` Python package as dependency.

### Flow

1. User saves a round (or clicks Refresh on landing page).
2. Stats service computes current aggregates.
3. Serializer formats recent N rounds + stats into structured context.
4. Single `openai.chat.completions.create()` call with system + user messages.
5. Response parsed as JSON array of 3-5 insight strings.
6. Cached in `insights_cache` table.
7. Landing page reads from cache — no API call on page load.

### Prompt structure

```
You are a golf improvement coach analyzing an amateur golfer's
round data. Generate exactly 5 independent insights as a JSON array.
Each insight should be 2-3 sentences, focus on a different aspect,
and relate findings to handicap impact.

Player: HCP {index}
Last {n} rounds:
{serialized round data with computed stats}

Handicap-relative strokes lost:
  Putting: {value}/round
  Short game: {value}/round
  Approach: {value}/round
  Tee shots: {value}/round
```

### Cost

~$0.01-0.05 per generation (GPT-4o). One call per round saved.
No Assistants API overhead — simpler, stateless, same quality.

---

## Stages

### Stage 1: Database & Round Model

**Goal:** SQLite database with round/hole storage, CRUD service.

Tasks:
- [ ] Add `db_path` to `config.py` settings
- [ ] Create `db/schema.sql` with `rounds`, `round_holes`, `insights_cache` tables
- [ ] Create `db/connection.py` — async-compatible SQLite connection manager
- [ ] Create `rounds/models.py` — Pydantic models for Round, RoundHole, RoundSummary
- [ ] Create `rounds/repository.py` — SQLite CRUD (create, read, update, delete)
- [ ] Create `rounds/service.py` — business logic (create round with course snapshot)
- [ ] Wire DB init into `main.py` startup
- [ ] Add `aiosqlite` to dependencies
- [ ] Write tests for round CRUD

**Done when:** A round can be created, hole data saved, retrieved, and deleted via service layer.

### Stage 2: Round Entry UI

**Goal:** Web form to create a round and enter hole-by-hole data.

Tasks:
- [ ] Create `round_create.html` — course/tee selection form (reuse catalog dropdown)
- [ ] Create `round_entry.html` — spreadsheet grid with 18 rows
- [ ] Add routes: `GET /rounds/new`, `POST /rounds`, `GET /rounds/{id}/edit`, `POST /rounds/{id}`
- [ ] Add round service + builder dependencies
- [ ] Inline JS for auto-totals, tab navigation, toggle inputs
- [ ] CSS for entry grid (extend `app.css`)
- [ ] Write tests for round creation and save routes

**Done when:** A user can create a round, enter all 18 holes of data, and save.

### Stage 3: Round History & Detail Views

**Goal:** Browse saved rounds and view filled-in scorecards.

Tasks:
- [ ] Create `round_list.html` — table of all rounds with headline stats
- [ ] Create `round_detail.html` — filled scorecard view (same layout as preview, but with data)
- [ ] Add routes: `GET /rounds`, `GET /rounds/{id}`, `POST /rounds/{id}/delete`
- [ ] Write tests for list and detail routes

**Done when:** A user can view all past rounds and drill into any single round.

### Stage 4: Stats & Landing Page Redesign

**Goal:** Computed stats on the landing page, new two-card layout.

Tasks:
- [ ] Create `rounds/stats.py` — aggregate functions, handicap-relative analysis, trends
- [ ] Redesign `home.html` — two action cards, quick stats section, recent rounds list
- [ ] Add stats service to dependencies
- [ ] Stats section conditionally renders only when rounds exist
- [ ] Write tests for stats calculations

**Done when:** Landing page shows avg score, GIR%, FIR%, putts, trend arrows, and recent rounds.

### Stage 5: LLM Coaching Insights

**Goal:** OpenAI-generated insights cached and displayed on landing page.

**Prerequisites:** OpenAI account with API access (see OpenAI Setup below).

Tasks:
- [ ] Add `openai` to dependencies
- [ ] Add `openai_api_key` to `config.py`
- [ ] Create `insights/serializers.py` — round data → structured prompt context
- [ ] Create `insights/prompts.py` — system instructions and user message templates
- [ ] Create `insights/service.py` — chat completion call, JSON parsing, cache read/write
- [ ] Add insights carousel to `home.html` (◄ ► navigation, Refresh button)
- [ ] Add route: `POST /insights/refresh`
- [ ] Auto-generate insights on round save
- [ ] Write tests (mock OpenAI calls)

**Done when:** Landing page shows 3-5 cycling coaching insights, refreshable on demand.

---

## OpenAI Setup

Stateless chat completions — no assistants or threads to manage.

### Secrets needed

| Secret           | Where to get it                                                    | Purpose                    |
|------------------|--------------------------------------------------------------------|----------------------------|
| `OPENAI_API_KEY` | [platform.openai.com/api-keys](https://platform.openai.com/api-keys) | Authenticates all API calls |

### Steps

1. Create an OpenAI account (if you don't have one).
2. Add a payment method (API is pay-per-use, separate from ChatGPT subscription).
3. Generate an API key at the link above.
4. Add it to your `.env` file:
   ```
   OPENAI_API_KEY=sk-...
   ```

No assistant setup script needed — the system prompt lives in code.

### Cost

~$0.01–0.05 per insight generation (GPT-4o). One call per round saved. Expect $1–2/month with regular use.

---

## Dependencies to Add

```toml
# pyproject.toml
dependencies = [
    # ... existing ...
    "aiosqlite>=0.20",     # Stage 1 — async SQLite
    "openai>=1.30",        # Stage 5 — Chat Completions API
]
```

## Config Additions

```python
# config.py
db_path: str = "data/golf_scorecards.db"       # Stage 1
openai_api_key: str = ""                         # Stage 5
```

## Files to .gitignore

```
data/golf_scorecards.db
.env
```
