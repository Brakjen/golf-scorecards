"""Shared helpers used by multiple route modules.

These functions are private to the ``web.routes`` package — they
compute Stableford / strokes-received maps from a round and assemble
the dashboard render context.
"""

from __future__ import annotations

import json
from typing import Any

from golf_scorecards.catalog.service import CatalogService
from golf_scorecards.insights.service import InsightsService
from golf_scorecards.rounds.models import Round, RoundHole
from golf_scorecards.rounds.service import RoundNotFoundError, RoundService
from golf_scorecards.rounds.stats import compute_quick_stats
from golf_scorecards.rounds.trends import compute_trends
from golf_scorecards.settings_repo import SettingsRepository


def strokes_received_map(
    all_holes: list[dict[str, Any]],
    playing_handicap: int | None,
    played_hole_numbers: set[int] | None = None,
) -> dict[int, int]:
    """Compute strokes received per hole from playing handicap.

    Always distributes the full 18-hole playing handicap across all 18
    holes, then returns only the holes actually played.  For 9-hole
    rounds this correctly ignores the strokes that fall on the
    unplayed nine.
    """
    if playing_handicap is None or not all_holes:
        return {}
    sign = 1 if playing_handicap >= 0 else -1
    base, remainder = divmod(abs(playing_handicap), len(all_holes))
    stroke_map: dict[int, int] = {h["hole_number"]: sign * base for h in all_holes}
    for h in sorted(all_holes, key=lambda c: c["handicap"])[:remainder]:
        stroke_map[h["hole_number"]] += sign
    if played_hole_numbers is not None:
        return {k: v for k, v in stroke_map.items() if k in played_hole_numbers}
    return stroke_map


def stableford_map(
    holes: list[RoundHole],
    strokes: dict[int, int],
) -> dict[int, int | None]:
    """Compute Stableford points per hole.

    Points are ``max(0, 2 - (net_score - par))`` where
    ``net_score = score - strokes_received``.
    """
    result: dict[int, int | None] = {}
    for h in holes:
        if h.score is None:
            result[h.hole_number] = None
        else:
            net = h.score - strokes.get(h.hole_number, 0)
            result[h.hole_number] = max(0, 2 - (net - h.par))
    return result


def total_stableford(r: Round) -> int | None:
    """Compute Stableford points relative to handicap for a round.

    Returns the difference between actual points and expected points
    (2 per scored hole).  Positive means played better than handicap.
    Returns ``None`` if no holes have been scored.
    """
    if not r.course_snapshot or not r.playing_handicap:
        return None
    snapshot = json.loads(r.course_snapshot)
    played = {h.hole_number for h in r.holes}
    strokes = strokes_received_map(snapshot["holes"], r.playing_handicap, played)
    pts = stableford_map(r.holes, strokes)
    scored = [v for v in pts.values() if v is not None]
    if not scored:
        return None
    expected = 2 * len(scored)
    return sum(scored) - expected


async def build_home_context(
    catalog_service: CatalogService,
    round_service: RoundService,
    settings_repo: SettingsRepository,
    insights_service: InsightsService | None,
) -> dict[str, Any]:
    """Assemble the template context shared by the dashboard render paths.

    The Q&A section is left at ``None`` here — callers attach it when
    rendering the page in response to an ``/ask`` submission, so reloads
    of ``/`` always start with a clean slate.
    """
    course_options = catalog_service.list_course_options()
    initial_course = course_options[0]
    initial_tee = initial_course["tees"][0]

    summaries = await round_service.list_rounds()
    recent = summaries[:3]

    handicap_index = await settings_repo.get("handicap_index")

    stats = None
    trends = None
    round_stableford: dict[str, int] = {}
    if summaries:
        stats_rounds = []
        for s in summaries[:5]:
            try:
                r = await round_service.get_round(s.id)
                stats_rounds.append(r)
            except RoundNotFoundError:
                continue
        if stats_rounds:
            stats = compute_quick_stats(stats_rounds)
            trends = compute_trends(stats_rounds, window=5)
        for r in stats_rounds:
            pts = total_stableford(r)
            if pts is not None:
                round_stableford[r.id] = pts

    insights: list[str] = []
    if insights_service is not None:
        cached = await insights_service.get_cached_insights()
        if cached:
            insights = cached

    return {
        "course_options": course_options,
        "initial_course_slug": initial_course["course_slug"],
        "initial_tee_name": initial_tee,
        "recent_rounds": recent,
        "round_stableford": round_stableford,
        "stats": stats,
        "trends": trends,
        "handicap_index": handicap_index,
        "insights": insights,
        "qa_entry": None,
        "qa_enabled": insights_service is not None,
    }
