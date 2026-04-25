"""Tests for web route handlers (home, preview, export)."""

from fastapi.testclient import TestClient

from golf_scorecards.main import app


def test_home_page_renders_course_form() -> None:
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    assert "Golf Scorecards" in response.text
    assert "Generate Scorecard" in response.text
    assert "Enter Round" in response.text
    assert "sola-golfklubb-forus" in response.text
    assert "Scoring mode" in response.text
    assert "Target score" in response.text
    assert "Handicap index" in response.text


def test_preview_renders_prefilled_scorecard() -> None:
    client = TestClient(app)

    response = client.post(
        "/scorecards/preview",
        data={
            "player_name": "Chris",
            "round_date": "2026-04-13",
            "course_slug": "sola-golfklubb-forus",
            "tee_name": "63",
        },
    )

    assert response.status_code == 200
    assert "Chris" in response.text
    assert "Sola golfklubb" in response.text
    assert "Forus" in response.text
    assert "Stroke play" in response.text
    assert "Score and per-hole metrics" in response.text
    assert "SZ in Reg" in response.text
    assert "Green Miss" in response.text


def test_preview_renders_adjusted_par_in_stroke_mode() -> None:
    client = TestClient(app)

    response = client.post(
        "/scorecards/preview",
        data={
            "player_name": "Chris",
            "round_date": "2026-04-13",
            "course_slug": "sola-golfklubb-forus",
            "tee_name": "58",
            "scoring_mode": "stroke",
            "target_score": "90",
            "handicap_index": "18.4",
            "handicap_profile": "men",
        },
    )

    assert response.status_code == 200
    assert "Adjusted Par" in response.text
    assert "Playing strokes" in response.text
    assert "70.6 / 139" in response.text
    assert ">21<" in response.text
    assert "2 Pts @" not in response.text


def test_preview_renders_stableford_columns() -> None:
    client = TestClient(app)

    response = client.post(
        "/scorecards/preview",
        data={
            "player_name": "Chris",
            "round_date": "2026-04-13",
            "course_slug": "sola-golfklubb-forus",
            "tee_name": "58",
            "scoring_mode": "stableford",
            "target_score": "90",
            "handicap_index": "18.4",
            "handicap_profile": "men",
        },
    )

    assert response.status_code == 200
    assert "Stableford" in response.text
    assert "2 Pts @" in response.text
    assert "Adjusted Par" not in response.text
    assert "The 2 Pts @ column shows" in response.text
    assert "Scoring-zone regulation uses the 2-point target minus 2." in response.text


def test_preview_returns_not_found_for_invalid_tee() -> None:
    client = TestClient(app)

    response = client.post(
        "/scorecards/preview",
        data={
            "player_name": "Chris",
            "round_date": "2026-04-13",
            "course_slug": "sola-golfklubb-forus",
            "tee_name": "999",
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Unknown tee '999' for course 'sola-golfklubb-forus'"