"""Tests for the stats computation module."""

from golf_scorecards.rounds.models import Round, RoundHole
from golf_scorecards.rounds.stats import QuickStats, compute_quick_stats

from datetime import datetime


def _make_hole(
    hole_number: int,
    par: int = 4,
    distance: int = 350,
    handicap: int = 9,
    score: int | None = None,
    putts: int | None = None,
    fir: int | None = None,
    gir: int | None = None,
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
        fir=fir,
        gir=gir,
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
    assert stats.gir_pct is None


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


def test_gir_percentage() -> None:
    """GIR percentage counts only holes with GIR data."""
    holes = [_make_hole(i, gir=1 if i <= 9 else 0) for i in range(1, 19)]
    r = _make_round(holes=holes)
    stats = compute_quick_stats([r])
    assert stats.gir_pct == 50.0


def test_fir_percentage_excludes_par3() -> None:
    """FIR percentage excludes par 3 holes."""
    holes = []
    for i in range(1, 19):
        par = 3 if i in (3, 8, 12, 16) else 4
        fir = 1 if i <= 9 else 0
        holes.append(_make_hole(i, par=par, fir=fir))
    r = _make_round(holes=holes)
    stats = compute_quick_stats([r])
    # 14 non-par-3 holes; holes 1-9 minus 3,8 = 7 hits; holes 10-18 minus 12,16 = 7 misses
    assert stats.fir_pct == 50.0


def test_up_and_down_pct() -> None:
    """Up-and-down percentage is computed from holes with U&D data."""
    holes = [_make_hole(i, up_and_down=1 if i <= 4 else 0) for i in range(1, 11)]
    r = _make_round(holes=holes)
    stats = compute_quick_stats([r])
    assert stats.up_and_down_pct == 40.0


def test_putts_per_gir() -> None:
    """Putts per GIR is computed from GIR=1 holes with putt data."""
    holes = [
        _make_hole(1, gir=1, putts=2),
        _make_hole(2, gir=1, putts=1),
        _make_hole(3, gir=0, putts=3),  # Not a GIR hole
        _make_hole(4, gir=1, putts=2),
    ]
    r = _make_round(holes=holes)
    stats = compute_quick_stats([r])
    # (2 + 1 + 2) / 3 = 1.67
    assert stats.putts_per_gir == 1.67


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
