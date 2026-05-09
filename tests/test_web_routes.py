"""Tests for the home page route."""

from fastapi.testclient import TestClient

from golf_scorecards.main import app


def test_unauthenticated_redirects_to_login() -> None:
    """Unauthenticated requests to / should redirect to /login."""
    with TestClient(app) as client:
        response = client.get("/", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_login_page_renders() -> None:
    """The login page should render without error."""
    with TestClient(app) as client:
        response = client.get("/login")

    assert response.status_code == 200
    assert "Log in" in response.text or "login" in response.text.lower()
