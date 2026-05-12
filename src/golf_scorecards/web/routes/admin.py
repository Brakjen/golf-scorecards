"""Admin routes: user management and impersonation."""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from golf_scorecards.config import get_settings
from golf_scorecards.web.dependencies import get_auth_service, get_templates

router = APIRouter(prefix="/admin")
templates = get_templates()


def _require_admin(request: Request) -> bool:
    """Check if the real user (not impersonated) is an admin."""
    admin = getattr(request.state, "admin_user", None)
    if admin:
        return True  # Already impersonating → they are admin
    user = getattr(request.state, "user", None)
    return user is not None and user.is_admin


def _count_orphaned() -> int:
    """Count rows with empty user_id across rounds and practice_sessions."""
    settings = get_settings()
    conn = sqlite3.connect(settings.db_path)
    try:
        rounds = conn.execute("SELECT COUNT(*) FROM rounds WHERE user_id = ''").fetchone()[0]
        sessions = conn.execute("SELECT COUNT(*) FROM practice_sessions WHERE user_id = ''").fetchone()[0]
        return rounds + sessions
    finally:
        conn.close()


# Pricing per million tokens (as of 2025)
_MODEL_PRICING: dict[str, tuple[float, float]] = {
    # (input $/M, output $/M)
    "gpt-4.1": (2.00, 8.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "o3": (2.00, 8.00),
}


def _get_usage_stats() -> dict:
    """Aggregate API usage from agent_usage_log."""
    settings = get_settings()
    conn = sqlite3.connect(settings.db_path)
    conn.row_factory = sqlite3.Row
    try:
        # Per-agent breakdown
        rows = conn.execute("""
            SELECT agent_key, model,
                   COUNT(*) AS calls,
                   SUM(prompt_tokens) AS prompt_tokens,
                   SUM(completion_tokens) AS completion_tokens,
                   SUM(cached) AS cached_tokens,
                   ROUND(AVG(latency_ms)) AS avg_latency_ms
            FROM agent_usage_log
            GROUP BY agent_key, model
            ORDER BY SUM(prompt_tokens + completion_tokens) DESC
        """).fetchall()

        agents = []
        total_prompt = 0
        total_completion = 0
        total_cached = 0
        total_cost = 0.0
        total_calls = 0

        for r in rows:
            prompt = r["prompt_tokens"] or 0
            completion = r["completion_tokens"] or 0
            cached = r["cached_tokens"] or 0
            model = r["model"]
            input_price, output_price = _MODEL_PRICING.get(model, (2.50, 10.00))

            # Cached tokens are charged at 50% of input price
            full_input = prompt - cached
            cost = (full_input * input_price + cached * input_price * 0.5 + completion * output_price) / 1_000_000

            agents.append({
                "agent_key": r["agent_key"],
                "model": model,
                "calls": r["calls"],
                "prompt_tokens": prompt,
                "completion_tokens": completion,
                "cached_tokens": cached,
                "avg_latency_ms": r["avg_latency_ms"],
                "cost": cost,
            })

            total_prompt += prompt
            total_completion += completion
            total_cached += cached
            total_cost += cost
            total_calls += r["calls"]

        return {
            "agents": agents,
            "total_prompt": total_prompt,
            "total_completion": total_completion,
            "total_cached": total_cached,
            "total_cost": total_cost,
            "total_calls": total_calls,
        }
    finally:
        conn.close()


@router.get("", response_class=HTMLResponse, response_model=None)
async def admin_panel(request: Request) -> Response:
    """Show admin panel with user list."""
    if not _require_admin(request):
        return RedirectResponse(url="/", status_code=303)

    auth_service = get_auth_service()
    users = await auth_service.list_users()

    # Who is the real admin?
    admin_user = getattr(request.state, "admin_user", None) or request.state.user
    impersonating_id = request.session.get("impersonate_user_id")
    orphaned_count = _count_orphaned()
    usage = _get_usage_stats()

    return templates.TemplateResponse(
        request=request,
        name="admin.html",
        context={
            "users": users,
            "admin_user": admin_user,
            "impersonating_id": impersonating_id,
            "orphaned_count": orphaned_count,
            "usage": usage,
        },
    )


@router.post("/impersonate/{user_id}", response_model=None)
async def impersonate(request: Request, user_id: str) -> Response:
    """Start impersonating another user."""
    if not _require_admin(request):
        return RedirectResponse(url="/", status_code=303)

    auth_service = get_auth_service()
    target = await auth_service.get_user_by_id(user_id)
    if target is None:
        return RedirectResponse(url="/admin", status_code=303)

    request.session["impersonate_user_id"] = user_id
    return RedirectResponse(url="/", status_code=303)


@router.post("/stop-impersonating", response_model=None)
async def stop_impersonating(request: Request) -> Response:
    """Stop impersonating and return to admin's own view."""
    request.session.pop("impersonate_user_id", None)
    return RedirectResponse(url="/admin", status_code=303)


@router.post("/claim-data/{user_id}", response_model=None)
async def claim_orphaned_data(request: Request, user_id: str) -> Response:
    """Assign all orphaned rows (user_id='') to the specified user."""
    if not _require_admin(request):
        return RedirectResponse(url="/", status_code=303)

    auth_service = get_auth_service()
    target = await auth_service.get_user_by_id(user_id)
    if target is None:
        return RedirectResponse(url="/admin", status_code=303)

    settings = get_settings()
    conn = sqlite3.connect(settings.db_path)
    try:
        conn.execute("UPDATE rounds SET user_id = ? WHERE user_id = ''", (user_id,))
        conn.execute("UPDATE practice_sessions SET user_id = ? WHERE user_id = ''", (user_id,))
        conn.commit()
    finally:
        conn.close()

    return RedirectResponse(url="/admin", status_code=303)
