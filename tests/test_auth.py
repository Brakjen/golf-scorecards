"""Tests for the cookie-session auth middleware."""

from fastapi.testclient import TestClient


def _build_app_with_password(password: str = "secret"):  # type: ignore[no-untyped-def]
    """Construct a fresh app with APP_PASSWORD set.

    We can't reuse the module-level app because it caches settings;
    we monkey-patch the cached settings before constructing it.
    """
    from golf_scorecards.config import Settings, get_settings
    from golf_scorecards.main import create_app

    get_settings.cache_clear()
    s = Settings(app_password=password, session_secret="test-secret")
    get_settings.cache_clear()

    # Re-prime the lru_cache with our test settings
    def _override() -> Settings:
        return s

    import golf_scorecards.config as cfg

    original = cfg.get_settings
    cfg.get_settings = _override  # type: ignore[assignment]
    try:
        app = create_app()
    finally:
        cfg.get_settings = original  # type: ignore[assignment]

    # The middleware reads via get_settings at request time, so override
    # that import path too.
    import golf_scorecards.web.auth as auth_mod

    auth_mod.get_settings = _override  # type: ignore[assignment]
    return app, original


def test_protected_path_redirects_to_login_when_no_session() -> None:
    app, restore = _build_app_with_password("hunter2")
    try:
        client = TestClient(app, follow_redirects=False)
        response = client.get("/")
        assert response.status_code == 303
        assert response.headers["location"] == "/login"
    finally:
        import golf_scorecards.web.auth as auth_mod

        auth_mod.get_settings = restore  # type: ignore[assignment]


def test_login_page_is_public() -> None:
    app, restore = _build_app_with_password("hunter2")
    try:
        client = TestClient(app)
        response = client.get("/login")
        assert response.status_code == 200
        assert "Sign in" in response.text
    finally:
        import golf_scorecards.web.auth as auth_mod

        auth_mod.get_settings = restore  # type: ignore[assignment]


def test_static_assets_are_public() -> None:
    app, restore = _build_app_with_password("hunter2")
    try:
        client = TestClient(app, follow_redirects=False)
        response = client.get("/static/styles/app.css")
        assert response.status_code == 200
    finally:
        import golf_scorecards.web.auth as auth_mod

        auth_mod.get_settings = restore  # type: ignore[assignment]


def test_health_is_public() -> None:
    app, restore = _build_app_with_password("hunter2")
    try:
        client = TestClient(app, follow_redirects=False)
        response = client.get("/health")
        assert response.status_code == 200
    finally:
        import golf_scorecards.web.auth as auth_mod

        auth_mod.get_settings = restore  # type: ignore[assignment]


def test_correct_password_logs_in_and_grants_access() -> None:
    app, restore = _build_app_with_password("hunter2")
    try:
        client = TestClient(app, follow_redirects=False)
        login = client.post("/login", data={"password": "hunter2"})
        assert login.status_code == 303
        assert login.headers["location"] == "/"

        # Cookie carried over by the client; landing page should now load.
        home = client.get("/")
        assert home.status_code == 200
    finally:
        import golf_scorecards.web.auth as auth_mod

        auth_mod.get_settings = restore  # type: ignore[assignment]


def test_wrong_password_redirects_back_to_login_with_error() -> None:
    app, restore = _build_app_with_password("hunter2")
    try:
        client = TestClient(app, follow_redirects=False)
        response = client.post("/login", data={"password": "wrong"})
        assert response.status_code == 303
        assert response.headers["location"] == "/login?error=1"

        # Still locked out
        home = client.get("/")
        assert home.status_code == 303
        assert home.headers["location"] == "/login"
    finally:
        import golf_scorecards.web.auth as auth_mod

        auth_mod.get_settings = restore  # type: ignore[assignment]


def test_logout_clears_session() -> None:
    app, restore = _build_app_with_password("hunter2")
    try:
        client = TestClient(app, follow_redirects=False)
        client.post("/login", data={"password": "hunter2"})
        assert client.get("/").status_code == 200

        logout = client.post("/logout")
        assert logout.status_code == 303
        assert logout.headers["location"] == "/login"

        assert client.get("/").status_code == 303
    finally:
        import golf_scorecards.web.auth as auth_mod

        auth_mod.get_settings = restore  # type: ignore[assignment]


def test_empty_password_disables_auth() -> None:
    """When APP_PASSWORD is unset, all routes are open (dev mode)."""
    from golf_scorecards.main import app

    client = TestClient(app)
    # The default test app has no password; / should load directly.
    response = client.get("/")
    assert response.status_code == 200
