"""Cookie-session authentication with multi-user support.

Users register with a username, password, and invite code. Login stores
``user_id`` in a signed session cookie. The ``RequireAuthMiddleware``
redirects unauthenticated requests to ``/login``.

If no users exist in the database the middleware is disabled (first-run
flow redirects to ``/register``).
"""

from __future__ import annotations

from typing import cast

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from golf_scorecards.auth.models import User
from golf_scorecards.config import get_settings
from golf_scorecards.web.dependencies import get_auth_service, get_templates

router = APIRouter()
templates = get_templates()


_PUBLIC_PATHS: frozenset[str] = frozenset({"/login", "/register", "/health"})
_PUBLIC_PREFIXES: tuple[str, ...] = ("/static",)


def _is_public(path: str) -> bool:
    """Return True if a path bypasses authentication."""
    if path in _PUBLIC_PATHS:
        return True
    return any(path.startswith(p) for p in _PUBLIC_PREFIXES)


class RequireAuthMiddleware(BaseHTTPMiddleware):
    """Redirect unauthenticated requests to the login page.

    Resolves ``user_id`` from the session and attaches the ``User``
    object to ``request.state.user`` for downstream handlers.
    """

    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        path = request.url.path
        if _is_public(path):
            return await call_next(request)

        user_id = request.session.get("user_id")
        if not user_id:
            return RedirectResponse(url="/login", status_code=303)

        auth_service = get_auth_service()
        user = await auth_service.get_user_by_id(user_id)
        if user is None:
            request.session.clear()
            return RedirectResponse(url="/login", status_code=303)

        # Impersonation: admin browsing as another user
        impersonating_id = request.session.get("impersonate_user_id")
        if impersonating_id and user.is_admin:
            target = await auth_service.get_user_by_id(impersonating_id)
            if target:
                request.state.user = target
                request.state.admin_user = user
            else:
                # Target user gone, clear impersonation
                request.session.pop("impersonate_user_id", None)
                request.state.user = user
                request.state.admin_user = None
        else:
            request.state.user = user
            request.state.admin_user = None

        return await call_next(request)


def get_current_user(request: Request) -> User:
    """Extract the authenticated user from request state.

    Args:
        request: The current request (must have passed auth middleware).

    Returns:
        The authenticated ``User``.
    """
    return request.state.user


# ── Login ────────────────────────────────────────────────────────────────

@router.get("/login", response_class=HTMLResponse, response_model=None)
async def login_form(
    request: Request, error: str | None = None,
) -> Response:
    """Render the login page (or redirect home if already authenticated)."""
    if request.session.get("user_id"):
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
    request: Request,
    username: str = Form(default=""),
    password: str = Form(default=""),
) -> Response:
    """Verify credentials and set the session cookie on success."""
    auth_service = get_auth_service()
    user = await auth_service.login(username, password)
    if user is None:
        return RedirectResponse(url="/login?error=1", status_code=303)
    request.session["user_id"] = user.id
    return RedirectResponse(url="/", status_code=303)


# ── Register ─────────────────────────────────────────────────────────────

@router.get("/register", response_class=HTMLResponse, response_model=None)
async def register_form(
    request: Request, error: str | None = None,
) -> Response:
    """Render the registration page."""
    if request.session.get("user_id"):
        return RedirectResponse(url="/", status_code=303)
    settings = get_settings()
    return cast(
        HTMLResponse,
        templates.TemplateResponse(
            request=request,
            name="register.html",
            context={"error": error, "require_invite": bool(settings.invite_code)},
        ),
    )


@router.post("/register", response_model=None)
async def register_submit(
    request: Request,
    username: str = Form(default=""),
    password: str = Form(default=""),
    display_name: str = Form(default=""),
    invite_code: str = Form(default=""),
) -> Response:
    """Create a new account and log in immediately."""
    auth_service = get_auth_service()
    result = await auth_service.register(username, password, display_name, invite_code)
    if isinstance(result, str):
        from urllib.parse import quote

        return RedirectResponse(url=f"/register?error={quote(result)}", status_code=303)
    request.session["user_id"] = result.id
    return RedirectResponse(url="/", status_code=303)


# ── Logout ───────────────────────────────────────────────────────────────

@router.post("/logout")
async def logout(request: Request) -> RedirectResponse:
    """Clear the session and return to the login page."""
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)


# ── Middleware installation ──────────────────────────────────────────────

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
