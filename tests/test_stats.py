"""Tests for the stats computation module."""

from datetime import datetime

from golf_scorecards.rounds.models import Round, RoundHole
from golf_scorecards.rounds.stats import compute_quick_stats


def _make_hole(
    hole_number: int,
    par: int = 4,
    distance: int = 350,
    handicap: int = 9,
    score: int | None = None,
    putts: int | None = None,
    penalty_strokes: int | None = None,
    up_and_down: int | None = None,
) -> RoundHole:
    """Create a hole with sensible defaults for testing."""
    return RoundHole(
        id=f"hole-{hole_number}",
        round_id="round-1",
        hole_number=hole_number,
        par=par,
        distance=distance,
        handicap=handicap,
        score=score,
        putts=putts,
        penalty_strokes=penalty_strokes,
        up_and_down=up_and_down,
    )


def _make_round(
    round_id: str = "round-1",
    holes: list[RoundHole] | None = None,
) -> Round:
    """Create a round with defaults for testing."""
    return Round(
        id=round_id,
        course_slug="test-course",
        tee_name="58",
        round_date=datetime.now().date(),
        course_snapshot="{}",
        created_at=datetime.now(),
        updated_at=datetime.now(),
        holes=holes or [],
    )


def test_empty_rounds() -> None:
    """compute_quick_stats with no rounds returns zero count and all None."""
    stats = compute_quick_stats([])
    assert stats.rounds_count == 0
    assert stats.avg_score is None


def test_avg_score() -> None:
    """Average score is computed from scored holes."""
    holes = [_make_hole(i, score=4) for i in range(1, 19)]
    r = _make_round(holes=holes)
    stats = compute_quick_stats([r])
    assert stats.rounds_count == 1
    assert stats.avg_score == 72.0


def test_avg_putts() -> None:
    """Average putts is computed from holes with putt data."""
    holes = [_make_hole(i, score=4, putts=2) for i in range(1, 19)]
    r = _make_round(holes=holes)
    stats = compute_quick_stats([r])
    assert stats.avg_putts == 36.0


def test_gir_removed() -> None:
    """QuickStats no longer has gir_pct."""
    stats = compute_quick_stats([])
    assert not hasattr(stats, "gir_pct")
    assert not hasattr(stats, "fir_pct")
    assert not hasattr(stats, "putts_per_gir")


def test_up_and_down_pct() -> None:
    """Up-and-down percentage is computed from holes with U&D data."""
    holes = [_make_hole(i, up_and_down=1 if i <= 4 else 0) for i in range(1, 11)]
    r = _make_round(holes=holes)
    stats = compute_quick_stats([r])
    assert stats.up_and_down_pct == 40.0


def test_multiple_rounds() -> None:
    """Stats are computed across multiple rounds."""
    r1_holes = [_make_hole(i, score=4, putts=2) for i in range(1, 19)]
    r2_holes = [
        _make_hole(i, score=5, putts=2)
        for i in range(1, 19)
    ]
    for h in r2_holes:
        h.model_config  # just accessing to ensure it's a proper model

    r1 = _make_round(round_id="r1", holes=r1_holes)
    r2 = _make_round(round_id="r2", holes=[
        RoundHole(
            id=f"r2-hole-{h.hole_number}",
            round_id="r2",
            hole_number=h.hole_number,
            par=h.par,
            distance=h.distance,
            handicap=h.handicap,
            score=5,
            putts=2,
        )
        for h in r2_holes
    ])
    stats = compute_quick_stats([r1, r2])
    assert stats.rounds_count == 2
    # (72 + 90) / 2 = 81
    assert stats.avg_score == 81.0
    assert stats.avg_putts == 36.0


def test_penalties() -> None:
    """Average penalties are computed across rounds."""
    holes = [_make_hole(i, penalty_strokes=1 if i <= 3 else 0) for i in range(1, 19)]
    r = _make_round(holes=holes)
    stats = compute_quick_stats([r])
    assert stats.avg_penalties == 3.0
