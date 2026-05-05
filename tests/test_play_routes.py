"""Tests for the on-course play surface (grid + per-hole guide)."""

from importlib.resources import files

import pytest
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.testclient import TestClient

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
    path = str(tmp_path) + "/test.db"  # type: ignore[operator]
    init_db_sync(path)
    return path


@pytest.fixture()
def client(db_path: str) -> TestClient:
    return TestClient(_make_test_app(db_path))


def _create_round(client: TestClient) -> str:
    resp = client.post(
        "/rounds",
        data={
            "course_slug": "sola-golfklubb-forus",
            "tee_name": "58",
            "round_date": "2026-04-25",
        },
        follow_redirects=False,
    )
    play_url = resp.headers["location"]
    return play_url.split("/rounds/")[1].split("/play")[0]


def test_play_grid_renders_18_tiles(client: TestClient) -> None:
    rid = _create_round(client)
    resp = client.get(f"/rounds/{rid}/play")
    assert resp.status_code == 200
    # All 18 hole tiles link to the per-hole page
    for n in range(1, 19):
        assert f"/rounds/{rid}/play/{n}" in resp.text
    # Default state is empty (no scores entered yet)
    assert "play-tile--empty" in resp.text


def test_play_hole_renders_four_panels(client: TestClient) -> None:
    rid = _create_round(client)
    resp = client.get(f"/rounds/{rid}/play/1")
    assert resp.status_code == 200
    # Four panel sections
    assert 'data-panel="1"' in resp.text
    assert 'data-panel="2"' in resp.text
    assert 'data-panel="3"' in resp.text
    assert 'data-panel="4"' in resp.text
    # Form submits to the per-hole save endpoint
    assert f'action="/rounds/{rid}/play/1"' in resp.text


def test_play_hole_save_persists_and_redirects_to_grid(
    client: TestClient,
) -> None:
    rid = _create_round(client)
    resp = client.post(
        f"/rounds/{rid}/play/3",
        data={"score": "4", "putts": "2", "penalty": "0", "nfs": "0", "action": "grid"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == f"/rounds/{rid}/play"

    # Tile for hole 3 should now show 'done' state (all key metrics filled)
    grid = client.get(f"/rounds/{rid}/play")
    assert "play-tile--done" in grid.text


def test_play_hole_save_with_action_next_redirects_to_next_hole(
    client: TestClient,
) -> None:
    rid = _create_round(client)
    resp = client.post(
        f"/rounds/{rid}/play/5",
        data={"score": "4", "putts": "2", "penalty": "0", "nfs": "0", "action": "next"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == f"/rounds/{rid}/play/6"


def test_partial_state_when_only_score_entered(client: TestClient) -> None:
    rid = _create_round(client)
    client.post(
        f"/rounds/{rid}/play/1",
        data={"score": "4", "action": "grid"},
        follow_redirects=False,
    )
    grid = client.get(f"/rounds/{rid}/play")
    assert "play-tile--partial" in grid.text


def test_partial_state_when_score_and_putts_but_not_trouble(
    client: TestClient,
) -> None:
    """Score + putts without penalty/nfs should still be partial (pink)."""
    rid = _create_round(client)
    client.post(
        f"/rounds/{rid}/play/2",
        data={"score": "5", "putts": "2", "action": "grid"},
        follow_redirects=False,
    )
    grid = client.get(f"/rounds/{rid}/play")
    assert "play-tile--partial" in grid.text


def test_play_hole_unknown_hole_returns_404(client: TestClient) -> None:
    rid = _create_round(client)
    resp = client.get(f"/rounds/{rid}/play/99")
    assert resp.status_code == 404


def test_play_grid_unknown_round_returns_404(client: TestClient) -> None:
    resp = client.get("/rounds/nonexistent/play")
    assert resp.status_code == 404
