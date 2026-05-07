"""Tests for multi-user cookie-session auth."""

import os
import tempfile

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def app_client():
    """Build a fresh app with a temp DB and return a TestClient."""
    from golf_scorecards.config import get_settings
    from golf_scorecards.web.dependencies import (
        get_auth_service,
        get_catalog_service,
        get_handicap_service,
        get_insights_service,
        get_practice_service,
        get_round_service,
        get_settings_repo,
        get_templates,
    )

    # Clear all lru_caches
    for fn in (
        get_settings, get_auth_service, get_round_service,
        get_practice_service, get_settings_repo, get_templates,
        get_catalog_service, get_handicap_service, get_insights_service,
    ):
        fn.cache_clear()

    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    os.environ["DB_PATH"] = tmp.name
    os.environ["SESSION_SECRET"] = "test-secret"
    os.environ["INVITE_CODE"] = "golf123"
    os.environ["APP_ENV"] = "test"

    get_settings.cache_clear()

    from golf_scorecards.main import create_app

    app = create_app()
    with TestClient(app, follow_redirects=False) as client:
        yield client

    # Cleanup
    for fn in (
        get_settings, get_auth_service, get_round_service,
        get_practice_service, get_settings_repo, get_templates,
        get_catalog_service, get_handicap_service, get_insights_service,
    ):
        fn.cache_clear()
    os.unlink(tmp.name)
    for key in ("DB_PATH", "SESSION_SECRET", "INVITE_CODE", "APP_ENV"):
        os.environ.pop(key, None)


def _register(client: TestClient, username: str = "alice", password: str = "secret99"):
    """Helper: register a user."""
    return client.post("/register", data={
        "username": username,
        "password": password,
        "display_name": "Alice",
        "invite_code": "golf123",
    })


def test_protected_path_redirects_to_login(app_client: TestClient) -> None:
    response = app_client.get("/")
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_login_page_is_public(app_client: TestClient) -> None:
    response = app_client.get("/login")
    assert response.status_code == 200
    assert "Sign in" in response.text


def test_register_page_is_public(app_client: TestClient) -> None:
    response = app_client.get("/register")
    assert response.status_code == 200
    assert "Create account" in response.text


def test_static_assets_are_public(app_client: TestClient) -> None:
    response = app_client.get("/static/styles/app.css")
    assert response.status_code == 200


def test_health_is_public(app_client: TestClient) -> None:
    response = app_client.get("/health")
    assert response.status_code == 200


def test_register_and_login(app_client: TestClient) -> None:
    reg = _register(app_client)
    assert reg.status_code == 303
    assert reg.headers["location"] == "/"

    # Session cookie set — should access home
    home = app_client.get("/")
    assert home.status_code == 200


def test_login_with_credentials(app_client: TestClient) -> None:
    _register(app_client, "bob", "pass1234")
    # Clear session by logging out
    app_client.post("/logout")

    login = app_client.post("/login", data={"username": "bob", "password": "pass1234"})
    assert login.status_code == 303
    assert login.headers["location"] == "/"


def test_wrong_password_rejects(app_client: TestClient) -> None:
    _register(app_client, "carol", "correct")
    app_client.post("/logout")

    login = app_client.post("/login", data={"username": "carol", "password": "wrong"})
    assert login.status_code == 303
    assert login.headers["location"] == "/login?error=1"


def test_invalid_invite_code_rejects(app_client: TestClient) -> None:
    reg = app_client.post("/register", data={
        "username": "mallory",
        "password": "secret99",
        "display_name": "Mallory",
        "invite_code": "wrong-code",
    })
    assert reg.status_code == 303
    assert "error=" in reg.headers["location"]


def test_logout_clears_session(app_client: TestClient) -> None:
    _register(app_client)
    assert app_client.get("/").status_code == 200

    logout = app_client.post("/logout")
    assert logout.status_code == 303
    assert logout.headers["location"] == "/login"

    assert app_client.get("/").status_code == 303
