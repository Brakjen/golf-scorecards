# Golf Scorecards — Project Narrative

## Overview

Golf Scorecards is a personal web application for recording, analysing, and improving upon golf round data. It replaces the paper scorecard with a mobile-first digital experience, adds statistical analysis across rounds, and provides LLM-powered coaching insights. The app is designed for a single user, deployed to the edge, and optimised for on-course use on a phone.

The tech stack is deliberately minimal: Python 3.12, FastAPI, Jinja2 server-side rendering, SQLite, and a single CSS file. There is no JavaScript framework — the app relies on progressive enhancement with small vanilla JS snippets for form interactivity.

---

## Architecture

### Application Structure

The codebase follows a modular domain-driven layout within a single Python package:

```
src/golf_scorecards/
├── catalog/         # Course data: models, repository, service
├── db/              # SQLite schema, connection management, migrations
├── handicap/        # Playing handicap computation
├── insights/        # LLM integration: prompts, serializers, caching
├── rounds/          # Round CRUD: models, repository, service, stats
├── web/             # FastAPI routes, auth, dependencies, templates
├── config.py        # Pydantic settings from env vars
└── main.py          # App factory and ASGI entry point
```

Each domain module exposes a **service** layer that encapsulates business logic, a **repository** for database operations, and **models** (Pydantic BaseModel classes) for data validation and serialisation. The web layer depends on services via FastAPI's dependency injection, keeping HTTP concerns separate from domain logic.

### Route Organisation

The web layer is split into purpose-specific routers:

| Router | Purpose |
|--------|---------|
| `dashboard.py` | The Play tab — the Enter Round form |
| `play.py` | On-course hole-by-hole entry surface |
| `rounds.py` | Round history, detail views, spreadsheet editing |
| `stats.py` | Aggregate statistics and trend charts |
| `coach.py` | LLM coaching insights and free-form Q&A |
| `settings.py` | Handicap index management and sign-out |
| `auth.py` | Cookie-session login |

Router order matters: `play` is registered before `rounds` so that static paths like `/rounds/new` and `/rounds/{id}/edit` match ahead of the dynamic `/rounds/{round_id}` capture.

---

## Design Choices

### Server-Side Rendering Over SPA

The app uses Jinja2 templates exclusively. This was a deliberate choice:

1. **Simplicity** — no build step, no node_modules, no client-side state management.
2. **Performance** — HTML arrives fully rendered; the phone doesn't need to download, parse, and execute a framework before showing content.
3. **Reliability on course** — cellular connections on a golf course are unreliable. Full page loads with server-rendered HTML work better than SPAs that depend on API calls and client-side hydration.

The only JavaScript in the app handles two things: dynamic tee selection in the Enter Round form (populating radio buttons based on the selected course), and swipeable panels on the per-hole play surface.

### SQLite with WAL Mode

SQLite was chosen because:

- A single-user app doesn't need PostgreSQL's concurrency model.
- The database lives on a persistent volume right next to the application — zero network latency for reads and writes.
- WAL (Write-Ahead Logging) mode allows concurrent reads during writes without locking.
- Backups are trivial: copy a single file.

The schema uses `CREATE TABLE IF NOT EXISTS` with additive migrations applied on every startup, making the database self-healing after a fresh deploy.

### Dark Theme and Mobile-First CSS

The design targets on-course use: outdoors, often in bright sunlight, always on a phone. The dark theme (`--paper: #121a12`, `--ink: #e4e8e4`) was chosen because the user prefers it, and the entire layout is built mobile-first with flex/grid. Desktop simply gets wider cards.

Key CSS decisions:

- **Single CSS file** — no preprocessor, no CSS-in-JS, no utility framework. Custom properties provide theming. The file is ~1900 lines and loads in one request.
- **Cache-busting** — the CSS link includes `?v=<timestamp>` generated at process start, so every deploy forces fresh asset loading on mobile browsers that aggressively cache.
- **Flex-wrap for stat pills** — round cards use `flex-wrap: wrap` so metrics naturally flow onto multiple lines on narrow screens instead of causing horizontal scroll.
- **`min-width: 0`** on form inputs — prevents `<input type="date">` from overflowing its grid cell on iOS, where the native date picker chrome has a larger intrinsic minimum width.

### Tab-Based Information Architecture

The app uses a persistent bottom tab bar with five sections:

| Tab | Content |
|-----|---------|
| ⛳ Play | Enter Round form — the primary action |
| 📋 Rounds | Round history with detail/play/edit links |
| 📊 Stats | Quick stats + trend sparklines |
| 🧠 Coach | LLM coaching insights + Ask the Coach Q&A |
| ⚙️ Settings | Handicap index, sign out |

Each tab is a real route (not an anchor scroll), so the browser back button works naturally, pages can be bookmarked, and the tab bar highlights correctly via server-side path matching.

The Play tab is intentionally lean — just the form. Stats, trends, insights, and round history each live on their own tab so the user isn't overwhelmed with information when their goal is simply to start recording a round.

### On-Course Play Surface

The play surface is designed for quick data entry between shots:

- **Grid view** (`/rounds/{id}/play`) — a 3-column grid of hole tiles. Each tile shows the hole number, par, and score. Tiles are colour-coded:
  - **Gray** — no data entered yet
  - **Pink/magenta** — partial data (e.g. score and putts, but no trouble metrics)
  - **Green** — fully complete (score + putts + penalty + NFS all recorded)

- **Hole detail** (`/rounds/{id}/play/{n}`) — a swipeable 4-panel form:
  1. Score & Putts (the essentials)
  2. Short Game (scoring zone, up & down, down in 3)
  3. Trouble (penalties, green miss direction, NFS)
  4. Notes (free text)

The "done" state requires that the user has explicitly filled in the Trouble panel metrics (penalty strokes and NFS), not just score and putts. This encourages complete data collection which feeds better statistical analysis later.

### Hole Metrics — What We Track and Why

| Metric | Purpose |
|--------|---------|
| Score | Gross strokes — the fundamental measurement |
| Putts | Putting efficiency; enables 3-putt tracking |
| Penalty strokes | Course management quality |
| Scoring zone in regulation | Did the approach reach the green or surrounds? |
| Up & down | Short game recovery success |
| Down in 3 | Alternative scrambling from further out |
| NFS (Non-Functional Strikes) | Chunks, tops, shanks — shots with zero forward progress |
| Green miss direction | Pattern detection for alignment issues |
| Notes | Context the numbers can't capture |

NFS is a particularly useful metric for mid-to-high handicappers. It captures the shots that are completely wasted (a topped ball that goes 10 metres, a chunk that stays in the rough). Traditional stats like "greens in regulation" don't distinguish between a miss that leaves a straightforward chip and a miss that costs two extra shots.

### LLM Coaching Integration

The Coach tab provides two features:

1. **Automated insights** — OpenAI GPT-4o analyses the last 5 rounds and produces 3 coaching insights: one positive, two improvement-focused. Insights are cached (keyed by a hash of the round IDs) so repeated page loads don't trigger API calls.

2. **Free-form Q&A** — the user can ask any question about their rounds. The entire round data set is serialised and sent as context along with the question. Responses are cached per-question.

The system prompt is carefully constructed:
- It includes YAML metric definitions so the LLM understands what each field means (e.g. that "SZ" is a checkbox that may be blank, not necessarily a failure).
- It's calibrated to the user's handicap index.
- It explicitly forbids generic advice — every insight must reference actual numbers.

### Authentication

A simple cookie-session model:

- `APP_PASSWORD` is set as an environment secret on Fly.io.
- A successful POST to `/login` sets `request.session["authed"] = True` in a signed cookie (Starlette's `SessionMiddleware` with `SESSION_SECRET`).
- `RequireAuthMiddleware` checks the session on every request; unauthenticated users are redirected to `/login`.
- If `APP_PASSWORD` is empty (local development), authentication is disabled entirely.

This is intentionally minimal — there's no user registration, no OAuth, no token refresh. It's a single-user app behind a password, and the session cookie is signed to prevent tampering.

---

## Deployment

### Infrastructure

The app runs on **Fly.io** in the `arn` region (Stockholm — closest to Norway):

- **Single machine** — shared-cpu-1x with 512MB RAM. More than enough for a single-user app with SQLite.
- **Persistent volume** — `golf_data` mounted at `/data` stores the SQLite database. The volume survives machine restarts and deploys.
- **Auto-stop/start** — the machine stops when idle and starts on incoming requests. This keeps costs near zero while maintaining sub-second cold-start times.
- **Force HTTPS** — all HTTP requests are redirected to HTTPS.
- **Health checks** — `/health` endpoint polled every 30 seconds.

### Docker Build

The Dockerfile uses a multi-stage build:

1. **Builder stage** — installs `uv` (the fast Python package manager), resolves dependencies from `uv.lock`, then installs the project.
2. **Runtime stage** — copies only the virtualenv and source code. Creates an unprivileged `app` user. The image is ~53MB.

Key runtime flags:
- `--proxy-headers --forwarded-allow-ips *` — trusts Fly's reverse proxy so `url_for()` generates `https://` URLs instead of `http://`.

### Deployment Workflow

```bash
fly deploy          # Build image, push, rolling restart
fly ssh sftp shell  # Upload DB: put local.db /data/upload.db
fly ssh console     # mv /data/upload.db /data/golf_scorecards.db
```

A gotcha we discovered: Fly's SFTP `put` won't overwrite an existing file (reports "file exists on VM"). The workaround is to upload to a different filename and then `mv` it into place via SSH console. If doing this, you must also `chown app:app` the file since SSH runs as root but the app runs as user `app`.

### Database Persistence

The `init_db_sync` function runs on every startup and:
1. Creates parent directories if they don't exist.
2. Executes `schema.sql` (all `CREATE TABLE IF NOT EXISTS`).
3. Applies additive column migrations (checking `PRAGMA table_info` before each `ALTER TABLE`).

This means a fresh deploy with an empty volume will self-provision the database, and an existing database will be gracefully migrated.

---

## Testing

The test suite uses pytest with `pytest-asyncio` for async service tests and FastAPI's `TestClient` for integration tests. At the time of writing: **86 tests, all passing**.

Tests cover:
- Route behaviour (status codes, redirects, rendered content assertions)
- Round CRUD operations (create, read, update, delete)
- Play surface state logic (tile colouring based on hole completeness)
- Insights service (caching, cache misses, input validation)
- Stats computation (averages, trends, stableford scoring)

The test database is always in-memory (`:memory:`) so tests are fast (~1 second for the full suite) and don't leave artefacts.

---

## What's Next

Potential future work:
- Sync local DB to remote on every round save (eliminate manual SFTP uploads)
- Per-hole historical comparison (how do I typically play hole 7?)
- Practice log integration
- Handicap differential calculation from round data
- PWA manifest + service worker for offline-first mobile experience
