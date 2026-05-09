# Feature Backlog

Living document of completed, in-progress, and proposed features.

## ✅ Completed (current branch `feature/round-tracking`)

- **Per-round coaching insights** — commit `78baa41`
  - 3 LLM-generated insights per round, cached by `(round_id, updated_at)`.
  - "Generate / Refresh" button on the round detail page.
  - Cache scoped via new `cache_key` column so dashboard and per-round
    insights don't overwrite each other.

- **Dashboard trend sparklines + hover detail charts** — commit `d900681`
  - Four per-round metrics for the last 5 rounds:
    Score vs handicap · Putts · Up & down % · 3-putt rate %.
  - Inline SVG, no JS, no chart library.
  - Hover (or keyboard focus) any card to reveal a 440 px chart with
    X/Y axes, gridlines, date labels, and a metric description.
  - 3-putts normalized to a rate so 9- and 18-hole rounds compare fairly.

## 🔜 Pending — chosen but not yet built

### Radar / spider chart (5-axis report card)
Visualise overall game shape on the dashboard.

- Axes: **Driving · Approach · Short game · Putting · Scoring**
- Each axis scored 0–100 from aggregate stats over the last *N* rounds.
- Pure SVG (shares infrastructure with the trend macros).
- Suggested scoring formulas (TBD when implementing):
  - **Driving** ← inverse of (NFS rate + penalty rate)
  - **Approach** ← scoring zone in regulation %
  - **Short game** ← (up-and-down % + down-in-3 %) / 2
  - **Putting** ← inverse of (avg putts/hole + 3-putt rate)
  - **Scoring** ← stableford-relative, normalised

## 💡 Backlog — proposed, not yet scheduled

### Ask the LLM (free-form Q&A)
A chat-style box where the user asks any question and the LLM answers
with the full round context loaded. Example prompt:
*"Based on my last 5 rounds, what should I improve in order to reduce
HCI by 5?"*

- Reuse `serialize_rounds()` for the context payload.
- Cache by `(question_hash, rounds_hash)` so repeat asks aren't re-billed.
- UI: textarea + submit, either on the dashboard or a dedicated `/ask` page.
- Optional "suggested questions" chips under the input.
- Consider streaming the response.

## 🚫 Skipped — not on the roadmap unless re-requested

- **Women's profile** — current target is men only.
- **Goal tracking** — user wants to think more before committing.
