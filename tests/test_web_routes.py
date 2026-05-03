"""Tests for the home page route."""

from fastapi.testclient import TestClient

from golf_scorecards.main import app


def test_home_page_renders_enter_round_card() -> None:
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    assert "Golf Scorecards" in response.text
    assert "Enter Round" in response.text
    assert "Start entering scores" in response.text
    assert "sola-golfklubb-forus" in response.text
