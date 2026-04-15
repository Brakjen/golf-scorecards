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
