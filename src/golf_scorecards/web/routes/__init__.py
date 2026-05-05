"""Aggregator that combines all sub-routers into a single ``router``.

Sub-router order matters: ``play`` is registered before ``rounds`` so
that the static ``/rounds/new`` and ``/rounds/{id}/edit`` routes match
ahead of the dynamic ``/rounds/{round_id}`` detail route.
"""

from fastapi import APIRouter

from golf_scorecards.web import auth
from golf_scorecards.web.routes import (
    coach,
    dashboard,
    play,
    rounds,
    settings,
    stats,
)

router = APIRouter()
router.include_router(auth.router)
router.include_router(dashboard.router)
router.include_router(play.router)
router.include_router(rounds.router)
router.include_router(stats.router)
router.include_router(coach.router)
router.include_router(settings.router)

__all__ = ["router"]
