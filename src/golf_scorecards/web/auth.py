"""Cookie-session authentication.

Single-user app: ``APP_PASSWORD`` is set as an environment variable.
A successful POST to ``/login`` sets ``request.session["authed"] = True``
in a signed cookie (signed with ``SESSION_SECRET``); the
``RequireAuthMiddleware`` then lets the request through. All other
paths except a tiny allow-list redirect to ``/login`` when the user
isn't authenticated.

If ``APP_PASSWORD`` is empty the middleware allows everything — useful
for local development.
"""

from __future__ import annotations

import hmac
from typing import cast

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from golf_scorecards.config import get_settings
from golf_scorecards.web.dependencies import get_templates

router = APIRouter()
templates = get_templates()


# Paths that bypass authentication. ``/static`` is mounted at the app
# level so its prefix is matched; everything else is an exact match.
_PUBLIC_PATHS: frozenset[str] = frozenset({"/login", "/health"})
_PUBLIC_PREFIXES: tuple[str, ...] = ("/static",)


def _is_public(path: str) -> bool:
    """Return True if a path bypasses authentication."""
    if path in _PUBLIC_PATHS:
        return True
    return any(path.startswith(p) for p in _PUBLIC_PREFIXES)


class RequireAuthMiddleware(BaseHTTPMiddleware):
    """Redirect unauthenticated requests to the login page.

    Runs after Starlette's ``SessionMiddleware`` so that
    ``request.session`` is populated. If ``APP_PASSWORD`` is empty the
    check is disabled entirely.
    """

    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        settings = get_settings()
        if not settings.app_password:
            return await call_next(request)

        path = request.url.path
        if _is_public(path) or request.session.get("authed"):
            return await call_next(request)

        return RedirectResponse(url="/login", status_code=303)


@router.get("/login", response_class=HTMLResponse, response_model=None)
async def login_form(
    request: Request, error: str | None = None,
) -> Response:
    """Render the login page (or redirect home if already authenticated)."""
    if request.session.get("authed"):
        return RedirectResponse(url="/", status_code=303)
    return cast(
        HTMLResponse,
        templates.TemplateResponse(
            request=request,
            name="login.html",
            context={"error": error},
        ),
    )


@router.post("/login", response_model=None)
async def login_submit(
    request: Request, password: str = Form(default=""),
) -> Response:
    """Verify the password and set the auth cookie on success."""
    expected = get_settings().app_password
    if expected and hmac.compare_digest(password, expected):
        request.session["authed"] = True
        return RedirectResponse(url="/", status_code=303)
    return RedirectResponse(url="/login?error=1", status_code=303)


@router.post("/logout")
async def logout(request: Request) -> RedirectResponse:
    """Clear the session and return to the login page."""
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)


def install_auth(app: ASGIApp) -> None:
    """Install the session and auth middlewares on a FastAPI app.

    Order matters: ``SessionMiddleware`` must run first so that
    ``request.session`` is available when ``RequireAuthMiddleware``
    inspects it. Starlette wraps middlewares outside-in, so the last
    one added is the outermost — we add session last.
    """
    settings = get_settings()
    from fastapi import FastAPI
    from starlette.middleware.sessions import SessionMiddleware

    fastapi_app = cast(FastAPI, app)
    fastapi_app.add_middleware(RequireAuthMiddleware)
    fastapi_app.add_middleware(
        SessionMiddleware,
        secret_key=settings.session_secret,
        session_cookie="gs_session",
        max_age=60 * 60 * 24 * 30,  # 30 days
        same_site="lax",
        https_only=settings.app_env == "production",
    )
