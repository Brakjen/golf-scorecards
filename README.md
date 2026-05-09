# golf-scorecards

Golf scorecard and performance metrics app.

## Backend setup

This repository is bootstrapped as a Python 3.12 project managed with `uv`.

### Install dependencies

```bash
uv sync --dev
```

### Run the API

```bash
uv run uvicorn golf_scorecards.main:app --reload
```

### Run checks

```bash
uv run pytest
uv run ruff check .
uv run mypy src
```

## Deploy to Fly.io

The repo ships a `Dockerfile` and `fly.toml` for a single-machine, single-volume
deployment (SQLite). One-time setup:

```bash
# 1. Create the app (pick a unique name)
fly apps create golf-scorecards-<yourhandle>
# Edit fly.toml `app = "..."` to match.

# 2. Create the persistent volume in the same region as the app
fly volumes create golf_data --region arn --size 1

# 3. Set the required secrets
fly secrets set \
  APP_PASSWORD="$(openssl rand -base64 18)" \
  SESSION_SECRET="$(openssl rand -hex 32)" \
  OPENAI_API_KEY="sk-..."

# 4. Deploy
fly deploy
```

Subsequent deploys are just `fly deploy`. The container listens on `:8080`,
serves `/health` for Fly's checks, and writes the SQLite DB to the
`/data` volume.


## Current scope

The initial scaffold includes:

- FastAPI application entrypoint
- Environment-backed settings via `.env`
- `pytest`, `ruff`, and `mypy` configuration in `pyproject.toml`
- A basic `/health` endpoint for smoke testing
- Manual course data packaged at `src/golf_scorecards/data/courses/no/manual_courses.json`

The domain model, persistence layer, and scorecard workflows described in `agents.md` still need to be implemented.

## Manual course data

The curated local course catalog now lives inside the application package so it can be versioned and shipped with the app.

- File: `src/golf_scorecards/data/courses/no/manual_courses.json`
- Shape: top-level `courses` array, with each entry representing a single course
- Access: `golf_scorecards.course_data.load_home_courses()`
