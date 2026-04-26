"""Deterministic stats computed from round hole data.

All functions are pure — they accept round/hole data and return computed
values without any database or I/O access.
"""

from __future__ import annotations

from dataclasses import dataclass

from golf_scorecards.rounds.models import Round


@dataclass(frozen=True)
class QuickStats:
    """Aggregated stats for a set of rounds.

    Attributes:
        rounds_count: Number of rounds included in the computation.
        avg_score: Mean gross score per round.
        avg_putts: Mean putts per round.
        avg_penalties: Mean penalty strokes per round.
        up_and_down_pct: Scrambling (up-and-down) percentage (0–100).
    """

    rounds_count: int
    avg_score: float | None
    avg_putts: float | None
    avg_penalties: float | None
    up_and_down_pct: float | None


def compute_quick_stats(rounds: list[Round]) -> QuickStats:
    """Compute aggregate stats across a list of rounds.

    Rounds whose holes have no score data are skipped for score-related
    averages. Each stat is computed independently — a round with scores
    but no GIR data still contributes to avg_score.

    Args:
        rounds: Rounds with fully loaded hole data.

    Returns:
        A ``QuickStats`` with all available aggregates, or ``None`` values
        when insufficient data exists.
    """
    if not rounds:
        return QuickStats(
            rounds_count=0,
            avg_score=None,
            avg_putts=None,
            avg_penalties=None,
            up_and_down_pct=None,
        )

    # ── Score & putts ────────────────────────────────────
    round_scores: list[int] = []
    round_putts: list[int] = []
    round_penalties: list[int] = []

    for r in rounds:
        scored = [h for h in r.holes if h.score is not None]
        if scored:
            round_scores.append(sum(h.score for h in scored if h.score is not None))
        putted = [h for h in r.holes if h.putts is not None]
        if putted:
            round_putts.append(sum(h.putts for h in putted if h.putts is not None))
        penalties = sum(
            h.penalty_strokes for h in r.holes if h.penalty_strokes is not None
        )
        round_penalties.append(penalties)

    avg_score = _avg(round_scores)
    avg_putts = _avg(round_putts)
    avg_penalties = _avg(round_penalties)

    # ── Up and down (scrambling) ─────────────────────────
    ud_attempts = 0
    ud_makes = 0
    for r in rounds:
        for h in r.holes:
            if h.up_and_down is not None:
                ud_attempts += 1
                if h.up_and_down == 1:
                    ud_makes += 1
    up_and_down_pct = (
        round(ud_makes / ud_attempts * 100, 1) if ud_attempts > 0 else None
    )

    return QuickStats(
        rounds_count=len(rounds),
        avg_score=round(avg_score, 1) if avg_score is not None else None,
        avg_putts=round(avg_putts, 1) if avg_putts is not None else None,
        avg_penalties=round(avg_penalties, 1) if avg_penalties is not None else None,
        up_and_down_pct=up_and_down_pct,
    )


def _avg(values: list[int]) -> float | None:
    """Compute the mean of a list of ints.

    Args:
        values: The values to average.

    Returns:
        The arithmetic mean, or ``None`` if the list is empty.
    """
    return sum(values) / len(values) if values else None
