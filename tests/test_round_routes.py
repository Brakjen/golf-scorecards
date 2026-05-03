"""Tests for round entry routes (create, entry form, save).

Builds a minimal FastAPI test app with only the round routes.
"""

from datetime import date
from importlib.resources import files

import pytest
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.testclient import TestClient
from starlette.templating import Jinja2Templates

from golf_scorecards.catalog.repository import CourseCatalogRepository
from golf_scorecards.catalog.service import CatalogService
from golf_scorecards.db.connection import init_db_sync
from golf_scorecards.rounds.repository import RoundRepository
from golf_scorecards.rounds.service import RoundService
from golf_scorecards.settings_repo import SettingsRepository
from golf_scorecards.web.dependencies import (
    get_catalog_service,
    get_round_service,
    get_settings_repo,
)
from golf_scorecards.web.routes import router


def _make_test_app(db_path: str) -> FastAPI:
    """Build a minimal FastAPI app for testing round routes.

    Overrides dependency injection to use a temporary database and avoid
    the full application startup.

    Args:
        db_path: Path to the temporary SQLite database.

    Returns:
        A configured FastAPI test application.
    """
    catalog_service = CatalogService(repository=CourseCatalogRepository())
    round_service = RoundService(repository=RoundRepository(db_path=db_path))
    settings_repo = SettingsRepository(db_path=db_path)
    static_dir = str(files("golf_scorecards").joinpath("static"))

    app = FastAPI()
    app.mount("/static", StaticFiles(directory=static_dir), name="static")
    app.dependency_overrides[get_catalog_service] = lambda: catalog_service
    app.dependency_overrides[get_round_service] = lambda: round_service
    app.dependency_overrides[get_settings_repo] = lambda: settings_repo
    app.include_router(router)

    return app


@pytest.fixture()
def db_path(tmp_path: object) -> str:
    """Create a temporary SQLite database.

    Args:
        tmp_path: Pytest temporary directory fixture.

    Returns:
        The filesystem path to the test database.
    """
    path = str(tmp_path) + "/test.db"  # type: ignore[operator]
    init_db_sync(path)
    return path


@pytest.fixture()
def client(db_path: str) -> TestClient:
    """Create a test client with a temporary database.

    Args:
        db_path: Path to the temporary test database.

    Returns:
        A ``TestClient`` for the test application.
    """
    app = _make_test_app(db_path)
    return TestClient(app)


@pytest.fixture()
def round_service(db_path: str) -> RoundService:
    """Create a round service with a temporary database.

    Args:
        db_path: Path to the temporary test database.

    Returns:
        A ``RoundService`` for test assertions.
    """
    return RoundService(repository=RoundRepository(db_path=db_path))


def test_round_create_form_renders(client: TestClient) -> None:
    """GET /rounds/new should render the round creation form."""
    response = client.get("/rounds/new")

    assert response.status_code == 200
    assert "Enter a round" in response.text
    assert "sola-golfklubb-forus" in response.text
    assert "Start entering scores" in response.text


def test_round_create_redirects_to_entry(client: TestClient) -> None:
    """POST /rounds should create a round and redirect to the entry form."""
    response = client.post(
        "/rounds",
        data={
            "course_slug": "sola-golfklubb-forus",
            "tee_name": "58",
            "player_name": "Test Player",
            "round_date": "2026-04-25",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert "/rounds/" in response.headers["location"]
    assert "/edit" in response.headers["location"]


def test_round_entry_form_renders(client: TestClient) -> None:
    """GET /rounds/{id}/edit should render the spreadsheet entry form."""
    # Create a round first
    create_response = client.post(
        "/rounds",
        data={
            "course_slug": "sola-golfklubb-forus",
            "tee_name": "58",
            "player_name": "Test Player",
            "round_date": "2026-04-25",
        },
        follow_redirects=False,
    )
    edit_url = create_response.headers["location"]

    response = client.get(edit_url)

    assert response.status_code == 200
    assert "Forus" in response.text
    assert "Test Player" in response.text
    assert "score_1" in response.text
    assert "score_18" in response.text
    assert "putts_1" in response.text
    assert "Save round" in response.text


def test_round_entry_form_not_found(client: TestClient) -> None:
    """GET /rounds/{id}/edit should return 404 for unknown round ID."""
    response = client.get("/rounds/nonexistent/edit")
    assert response.status_code == 404


def test_round_save_persists_scores(client: TestClient, db_path: str) -> None:
    """POST /rounds/{id} should save hole data and redirect back."""
    # Create a round
    create_response = client.post(
        "/rounds",
        data={
            "course_slug": "sola-golfklubb-forus",
            "tee_name": "58",
            "player_name": "Test",
            "round_date": "2026-04-25",
        },
        follow_redirects=False,
    )
    edit_url = create_response.headers["location"]
    round_id = edit_url.split("/rounds/")[1].split("/edit")[0]

    # Submit scores for all 18 holes
    form_data: dict[str, str] = {}
    for i in range(1, 19):
        form_data[f"score_{i}"] = "4"
        form_data[f"putts_{i}"] = "2"

    save_response = client.post(
        f"/rounds/{round_id}",
        data=form_data,
        follow_redirects=False,
    )

    assert save_response.status_code == 303
    assert save_response.headers["location"] == f"/rounds/{round_id}"

    # Verify scores persisted by loading the detail view
    detail_response = client.get(f"/rounds/{round_id}")
    assert detail_response.status_code == 200
    # Detail view should show the total score (4*18=72)
    assert "72" in detail_response.text


def test_round_save_not_found(client: TestClient) -> None:
    """POST /rounds/{id} should return 404 for unknown round ID."""
    response = client.post(
        "/rounds/nonexistent",
        data={"score_1": "4"},
    )
    assert response.status_code == 404


def test_round_create_invalid_course(client: TestClient) -> None:
    """POST /rounds with invalid course slug should return 404."""
    response = client.post(
        "/rounds",
        data={
            "course_slug": "nonexistent-course",
            "tee_name": "58",
        },
    )
    assert response.status_code == 404


def test_round_create_defaults_date(client: TestClient) -> None:
    """POST /rounds without a date should use today's date."""
    create_response = client.post(
        "/rounds",
        data={
            "course_slug": "sola-golfklubb-forus",
            "tee_name": "58",
        },
        follow_redirects=False,
    )

    assert create_response.status_code == 303
    edit_url = create_response.headers["location"]

    # Load the entry form and check today's date is shown
    entry_response = client.get(edit_url)
    assert entry_response.status_code == 200
    assert date.today().isoformat() in entry_response.text


# ── Round history & detail tests ─────────────────────────────────────


def test_round_list_empty(client: TestClient) -> None:
    """GET /rounds with no data should render empty state."""
    response = client.get("/rounds")
    assert response.status_code == 200
    assert "Round history" in response.text
    assert "No rounds recorded yet" in response.text


def test_round_list_shows_rounds(client: TestClient) -> None:
    """GET /rounds should list rounds after creation."""
    client.post(
        "/rounds",
        data={
            "course_slug": "sola-golfklubb-forus",
            "tee_name": "58",
            "player_name": "Tester",
            "round_date": "2026-04-20",
        },
        follow_redirects=False,
    )

    response = client.get("/rounds")
    assert response.status_code == 200
    assert "Tester" in response.text
    assert "Apr 20, 2026" in response.text


def test_round_detail_renders(client: TestClient) -> None:
    """GET /rounds/{id} should render the read-only detail view."""
    create_response = client.post(
        "/rounds",
        data={
            "course_slug": "sola-golfklubb-forus",
            "tee_name": "58",
            "player_name": "Detail Player",
            "round_date": "2026-04-20",
        },
        follow_redirects=False,
    )
    edit_url = create_response.headers["location"]
    round_id = edit_url.split("/rounds/")[1].split("/edit")[0]

    response = client.get(f"/rounds/{round_id}")
    assert response.status_code == 200
    assert "Forus" in response.text
    assert "Detail Player" in response.text
    assert "Edit scores" in response.text
    assert "Delete" in response.text


def test_round_detail_with_scores(client: TestClient) -> None:
    """GET /rounds/{id} should display scores and computed stats."""
    create_response = client.post(
        "/rounds",
        data={
            "course_slug": "sola-golfklubb-forus",
            "tee_name": "58",
            "player_name": "Scorer",
            "round_date": "2026-04-20",
        },
        follow_redirects=False,
    )
    edit_url = create_response.headers["location"]
    round_id = edit_url.split("/rounds/")[1].split("/edit")[0]

    # Submit scores
    form_data: dict[str, str] = {}
    for i in range(1, 19):
        form_data[f"score_{i}"] = "4"
        form_data[f"putts_{i}"] = "2"
    client.post(f"/rounds/{round_id}", data=form_data, follow_redirects=False)

    response = client.get(f"/rounds/{round_id}")
    assert response.status_code == 200
    # Total score = 4 * 18 = 72
    assert "72" in response.text
    # Total putts = 2 * 18 = 36
    assert "36" in response.text


def test_round_detail_not_found(client: TestClient) -> None:
    """GET /rounds/{id} should return 404 for unknown round ID."""
    response = client.get("/rounds/nonexistent")
    assert response.status_code == 404


def test_round_delete(client: TestClient) -> None:
    """POST /rounds/{id}/delete should remove the round and redirect."""
    create_response = client.post(
        "/rounds",
        data={
            "course_slug": "sola-golfklubb-forus",
            "tee_name": "58",
            "round_date": "2026-04-20",
        },
        follow_redirects=False,
    )
    edit_url = create_response.headers["location"]
    round_id = edit_url.split("/rounds/")[1].split("/edit")[0]

    delete_response = client.post(
        f"/rounds/{round_id}/delete",
        follow_redirects=False,
    )
    assert delete_response.status_code == 303
    assert delete_response.headers["location"] == "/rounds"

    # Verify round is gone
    detail_response = client.get(f"/rounds/{round_id}")
    assert detail_response.status_code == 404


def test_round_delete_not_found(client: TestClient) -> None:
    """POST /rounds/{id}/delete should return 404 for unknown round ID."""
    response = client.post("/rounds/nonexistent/delete")
    assert response.status_code == 404


def test_round_create_front_9(client: TestClient) -> None:
    """POST /rounds with holes_played=front_9 should create a 9-hole round."""
    create_response = client.post(
        "/rounds",
        data={
            "course_slug": "sola-golfklubb-forus",
            "tee_name": "58",
            "player_name": "Nine Holer",
            "round_date": "2026-04-25",
            "holes_played": "front_9",
        },
        follow_redirects=False,
    )
    assert create_response.status_code == 303
    edit_url = create_response.headers["location"]

    # Entry form should only show holes 1–9
    entry_response = client.get(edit_url)
    assert entry_response.status_code == 200
    assert "score_1" in entry_response.text
    assert "score_9" in entry_response.text
    assert "score_10" not in entry_response.text
    assert "Front 9" in entry_response.text


def test_round_create_back_9(client: TestClient) -> None:
    """POST /rounds with holes_played=back_9 should create a back-9 round."""
    create_response = client.post(
        "/rounds",
        data={
            "course_slug": "sola-golfklubb-forus",
            "tee_name": "58",
            "round_date": "2026-04-25",
            "holes_played": "back_9",
        },
        follow_redirects=False,
    )
    assert create_response.status_code == 303
    edit_url = create_response.headers["location"]

    entry_response = client.get(edit_url)
    assert entry_response.status_code == 200
    assert "score_10" in entry_response.text
    assert "score_18" in entry_response.text
    assert 'name="score_1"' not in entry_response.text
    assert 'name="score_9"' not in entry_response.text
    assert "Back 9" in entry_response.text
