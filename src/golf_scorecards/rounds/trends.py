"""Per-round time series for trend charts on the dashboard.

Pure functions that derive a small set of comparable metrics from
recently played rounds, suitable for rendering as inline SVG sparklines.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date

from golf_scorecards.rounds.models import Round


@dataclass(frozen=True)
class TrendPoint:
    """A single point on a trend series.

    Attributes:
        round_date: Date the round was played.
        value: Numeric value for the metric, or ``None`` if unavailable.
    """

    round_date: date
    value: float | None


@dataclass(frozen=True)
class TrendSeries:
    """A named ordered series of trend points (oldest → newest).

    Attributes:
        key: Stable identifier (``"score_vs_ph"``, ``"putts"``, …).
        label: Human-readable label for display.
        unit: Optional unit suffix (``"%"`` or empty).
        points: Points in chronological order (oldest first).
        higher_is_better: Whether higher values indicate better play.
    """

    key: str
    label: str
    unit: str
    points: list[TrendPoint]
    higher_is_better: bool


@dataclass(frozen=True)
class Trends:
    """Container for all trend series shown on the dashboard.

    Attributes:
        rounds_count: Number of rounds the trends are based on.
        series: Ordered list of series (display order).
    """

    rounds_count: int
    series: list[TrendSeries]


def compute_trends(rounds: list[Round], window: int = 5) -> Trends:
    """Compute trend series across the most recent ``window`` rounds.

    Rounds are expected newest-first (matching ``RoundService.list_rounds``);
    the resulting series are reordered oldest-first so charts read left
    to right.

    Args:
        rounds: Rounds with full hole data, newest-first.
        window: Maximum number of recent rounds to include.

    Returns:
        A ``Trends`` object with one series per metric. Returns an empty
        result when fewer than two rounds are available (a single point
        is not a meaningful trend).
    """
    selected = rounds[:window]
    if len(selected) < 2:
        return Trends(rounds_count=len(selected), series=[])

    chronological = list(reversed(selected))

    score_vs_ph: list[TrendPoint] = []
    putts: list[TrendPoint] = []
    scrambling: list[TrendPoint] = []
    three_putts: list[TrendPoint] = []

    for r in chronological:
        score_vs_ph.append(TrendPoint(r.round_date, _score_vs_ph(r)))
        putts.append(TrendPoint(r.round_date, _putts_total(r)))
        scrambling.append(TrendPoint(r.round_date, _scrambling_pct(r)))
        three_putts.append(TrendPoint(r.round_date, _three_putts(r)))

    series = [
        TrendSeries(
            key="score_vs_ph",
            label="Score vs handicap",
            unit="",
            points=score_vs_ph,
            higher_is_better=False,
        ),
        TrendSeries(
            key="putts",
            label="Putts",
            unit="",
            points=putts,
            higher_is_better=False,
        ),
        TrendSeries(
            key="scrambling",
            label="Up & down",
            unit="%",
            points=scrambling,
            higher_is_better=True,
        ),
        TrendSeries(
            key="three_putts",
            label="3-putt rate",
            unit="%",
            points=three_putts,
            higher_is_better=False,
        ),
    ]
    return Trends(rounds_count=len(chronological), series=series)


# ── Per-round metrics ────────────────────────────────────


def _score_vs_ph(r: Round) -> float | None:
    """Gross score relative to expected (par on played holes + PH share).

    For 9-hole rounds the playing handicap is prorated to the played
    holes so the metric stays comparable across formats. Returns
    ``None`` when no holes are scored.
    """
    scored = [h for h in r.holes if h.score is not None]
    if not scored or r.playing_handicap is None:
        return None
    total_score = sum(h.score for h in scored if h.score is not None)
    total_par = sum(h.par for h in scored)
    ph_share = r.playing_handicap * len(scored) / 18
    return float(total_score - (total_par + ph_share))


def _putts_total(r: Round) -> float | None:
    """Total putts for the round, or ``None`` if no putts recorded."""
    putted = [h.putts for h in r.holes if h.putts is not None]
    if not putted:
        return None
    return float(sum(putted))


def _stableford_rel(r: Round) -> float | None:
    """Stableford points relative to handicap (sum − 2 × scored holes).

    Currently unused on the dashboard (the round cards already show
    this as a blue pill, and over the long run it mirrors
    ``_score_vs_ph`` with the opposite sign), but kept here for
    potential reuse elsewhere.
    """
    if not r.course_snapshot or r.playing_handicap is None:
        return None
    try:
        snapshot = json.loads(r.course_snapshot)
    except (ValueError, TypeError):
        return None
    all_holes = snapshot.get("holes", [])
    if not all_holes:
        return None
    played = {h.hole_number for h in r.holes}
    strokes_map = _strokes_received_map(all_holes, r.playing_handicap, played)
    scored = 0
    points = 0
    for h in r.holes:
        if h.score is None:
            continue
        net = h.score - strokes_map.get(h.hole_number, 0)
        points += max(0, 2 - (net - h.par))
        scored += 1
    if scored == 0:
        return None
    return float(points - 2 * scored)


def _scrambling_pct(r: Round) -> float | None:
    """Up-and-down conversion percentage on holes where it was tracked.

    Counts any hole flagged ``up_and_down=1`` (got out of trouble in
    two strokes — typically chip + putt) regardless of whether the
    final score was par. Denominator is the number of holes with the
    metric tracked.
    """
    attempts = [h.up_and_down for h in r.holes if h.up_and_down is not None]
    if not attempts:
        return None
    makes = sum(1 for v in attempts if v == 1)
    return round(makes / len(attempts) * 100, 1)


def _three_putts(r: Round) -> float | None:
    """Percentage of putted holes with 3 or more putts (0–100).

    Using a rate keeps 9- and 18-hole rounds comparable.  Returns
    ``None`` when no putts were tracked.
    """
    putted = [h.putts for h in r.holes if h.putts is not None]
    if not putted:
        return None
    threes = sum(1 for p in putted if p is not None and p >= 3)
    return round(threes / len(putted) * 100, 1)


# ── Helpers ──────────────────────────────────────────────


def _strokes_received_map(
    all_holes: list[dict],
    playing_handicap: int,
    played_hole_numbers: set[int],
) -> dict[int, int]:
    """Distribute the 18-hole playing handicap across all 18 holes.

    Mirrors the logic in ``web.routes._strokes_received_map`` but kept
    private here so this module has no web-layer dependency.
    """
    if not all_holes:
        return {}
    sign = 1 if playing_handicap >= 0 else -1
    base, remainder = divmod(abs(playing_handicap), len(all_holes))
    stroke_map: dict[int, int] = {h["hole_number"]: sign * base for h in all_holes}
    for h in sorted(all_holes, key=lambda c: c["handicap"])[:remainder]:
        stroke_map[h["hole_number"]] += sign
    return {k: v for k, v in stroke_map.items() if k in played_hole_numbers}
