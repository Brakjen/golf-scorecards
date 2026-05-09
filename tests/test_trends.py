"""Tests for the trend computation module."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime

from golf_scorecards.rounds.models import Round, RoundHole
from golf_scorecards.rounds.trends import compute_trends


def _hole(
    n: int,
    *,
    par: int = 4,
    handicap: int | None = None,
    score: int | None = None,
    putts: int | None = None,
    up_and_down: int | None = None,
) -> RoundHole:
    return RoundHole(
        id=f"h{n}",
        round_id="r",
        hole_number=n,
        par=par,
        distance=350,
        handicap=handicap if handicap is not None else n,
        score=score,
        putts=putts,
        up_and_down=up_and_down,
    )


def _snapshot_18_par_4() -> str:
    holes = [
        {"hole_number": i, "par": 4, "distance": 350, "handicap": i}
        for i in range(1, 19)
    ]
    return json.dumps({"course_name": "Test", "tee_name": "63", "holes": holes})


def _round(
    rid: str,
    rdate: date,
    holes: list[RoundHole],
    *,
    playing_handicap: int = 18,
) -> Round:
    now = datetime.now(UTC)
    return Round(
        id=rid,
        course_slug="test",
        tee_name="63",
        round_date=rdate,
        handicap_index=18.0,
        playing_handicap=playing_handicap,
        course_rating=72.0,
        slope_rating=130,
        course_snapshot=_snapshot_18_par_4(),
        created_at=now,
        updated_at=now,
        holes=holes,
    )


class TestComputeTrends:
    def test_empty_returns_no_series(self) -> None:
        result = compute_trends([])
        assert result.rounds_count == 0
        assert result.series == []

    def test_single_round_returns_no_series(self) -> None:
        # Trends require at least 2 points to be meaningful.
        r = _round(
            "r1", date(2026, 4, 1), [_hole(i, score=4, putts=2) for i in range(1, 19)],
        )
        result = compute_trends([r])
        assert result.rounds_count == 1
        assert result.series == []

    def test_two_rounds_produces_all_series(self) -> None:
        r1 = _round(
            "r1", date(2026, 4, 1), [_hole(i, score=5, putts=2) for i in range(1, 19)],
        )
        r2 = _round(
            "r2", date(2026, 4, 8), [_hole(i, score=4, putts=2) for i in range(1, 19)],
        )
        # newest first (matches RoundService.list_rounds)
        result = compute_trends([r2, r1])
        assert result.rounds_count == 2
        keys = [s.key for s in result.series]
        assert keys == [
            "score_vs_ph",
            "putts",
            "scrambling",
            "three_putts",
        ]

    def test_chronological_ordering(self) -> None:
        # Older round first in series; newer last.
        r_old = _round(
            "r_old",
            date(2026, 4, 1),
            [_hole(i, score=6, putts=2) for i in range(1, 19)],
        )
        r_new = _round(
            "r_new",
            date(2026, 4, 8),
            [_hole(i, score=4, putts=2) for i in range(1, 19)],
        )
        result = compute_trends([r_new, r_old])
        score_series = next(s for s in result.series if s.key == "score_vs_ph")
        assert score_series.points[0].round_date == date(2026, 4, 1)
        assert score_series.points[-1].round_date == date(2026, 4, 8)
        # scoring better → value decreases
        assert score_series.points[0].value > score_series.points[-1].value
        assert score_series.higher_is_better is False

    def test_three_putts_rate(self) -> None:
        holes = [_hole(i, score=4, putts=3 if i <= 4 else 2) for i in range(1, 19)]
        r1 = _round("r1", date(2026, 4, 1), holes)
        r2 = _round(
            "r2", date(2026, 4, 8), [_hole(i, score=4, putts=2) for i in range(1, 19)],
        )
        result = compute_trends([r2, r1])
        three_putt_series = next(s for s in result.series if s.key == "three_putts")
        # 4 of 18 holes had 3+ putts → 22.2%
        assert three_putt_series.points[0].value == 22.2
        assert three_putt_series.points[-1].value == 0.0
        assert three_putt_series.unit == "%"

    def test_scrambling_pct(self) -> None:
        holes_a = [
            _hole(i, score=4, putts=2, up_and_down=(1 if i % 2 == 0 else 0))
            for i in range(1, 19)
        ]
        r1 = _round("r1", date(2026, 4, 1), holes_a)
        r2 = _round(
            "r2", date(2026, 4, 8), [_hole(i, score=4, putts=2) for i in range(1, 19)],
        )
        result = compute_trends([r2, r1])
        scr = next(s for s in result.series if s.key == "scrambling")
        assert scr.points[0].value == 50.0  # 9 of 18 attempts converted
        assert scr.points[-1].value is None  # no attempts tracked

    def test_window_limits_rounds(self) -> None:
        rounds = [
            _round(
                f"r{i}",
                date(2026, 4, i + 1),
                [_hole(h, score=4, putts=2) for h in range(1, 19)],
            )
            for i in range(7)
        ]
        # newest-first
        result = compute_trends(list(reversed(rounds)), window=5)
        assert result.rounds_count == 5
