"""Tests for match play scoring computation."""

import pytest

from golf_scorecards.rounds.match import compute_match_result
from golf_scorecards.rounds.models import RoundHole


def _hole(num: int, result: str | None = None) -> RoundHole:
    return RoundHole(
        id=f"h{num}", round_id="r1", hole_number=num,
        par=4, distance=350, handicap=num, hole_result=result,
    )


class TestComputeMatchResult:
    def test_no_results(self) -> None:
        holes = [_hole(i) for i in range(1, 19)]
        mr = compute_match_result(holes)
        assert mr.result_text == "—"
        assert mr.is_complete is False
        assert mr.closed_at is None

    def test_all_halved(self) -> None:
        holes = [_hole(i, "halve") for i in range(1, 19)]
        mr = compute_match_result(holes)
        assert mr.result_text == "AS"
        assert mr.holes_halved == 18
        assert mr.is_complete is True

    def test_win_early(self) -> None:
        # Win first 10 → lead=10 with 8 remaining → closed at hole 10
        holes = [_hole(i, "win") for i in range(1, 11)]
        holes += [_hole(i) for i in range(11, 19)]
        mr = compute_match_result(holes)
        assert mr.is_complete is True
        assert mr.result_text == "W 10&8"
        assert mr.closed_at == 10

    def test_loss_3_and_2(self) -> None:
        # Lose 8 of first 16 holes, win 5, halve 3 → down 3 with 2 to play
        results = (
            ["loss"] * 3 + ["win"] * 2 + ["halve"] + ["loss"] * 2
            + ["win"] * 2 + ["halve"] + ["loss"] * 2 + ["win"] + ["halve"]
            + ["loss"]
        )
        holes = [_hole(i + 1, r) for i, r in enumerate(results)]
        holes += [_hole(17), _hole(18)]
        mr = compute_match_result(holes)
        assert mr.is_complete is True
        assert mr.result_text == "L 3&2"
        assert mr.closed_at == 16

    def test_win_2_up_after_18(self) -> None:
        # Alternating wins/losses — never closes early, decided on 18
        results = ["win", "loss"] * 9  # 9 wins, 9 losses = AS
        results[17] = "win"  # make last hole a win → 10W, 8L = 2 UP
        # But check: does it close early?  Let's trace:
        # After each pair W,L the lead stays near 0-1, never > remaining
        holes = [_hole(i + 1, r) for i, r in enumerate(results)]
        mr = compute_match_result(holes)
        assert mr.result_text == "W 2 UP"
        assert mr.is_complete is True
        assert mr.closed_at is None  # went all 18

    def test_in_progress(self) -> None:
        holes = [_hole(1, "win"), _hole(2, "halve"), _hole(3, "loss")]
        holes += [_hole(i) for i in range(4, 19)]
        mr = compute_match_result(holes)
        assert mr.is_complete is False
        assert mr.result_text == "AS thru 3"

    def test_in_progress_leading(self) -> None:
        holes = [_hole(1, "win"), _hole(2, "win")]
        holes += [_hole(i) for i in range(3, 19)]
        mr = compute_match_result(holes)
        assert mr.result_text == "2 UP thru 2"
        assert mr.is_complete is False

    def test_hole_status_tracking(self) -> None:
        holes = [
            _hole(1, "win"), _hole(2, "loss"), _hole(3, "win"),
        ]
        holes += [_hole(i) for i in range(4, 19)]
        mr = compute_match_result(holes)
        assert mr.hole_status == {1: "1 UP", 2: "AS", 3: "1 UP"}

    def test_closes_at_correct_hole(self) -> None:
        # 7 wins in a row → after hole 7, lead=7 with 11 remaining
        # Not closed yet (7 < 11). After hole 10 win → lead=10, remaining=8
        # 10 > 8 → closed at hole 10
        holes = [_hole(i, "win") for i in range(1, 11)]
        holes += [_hole(i) for i in range(11, 19)]
        mr = compute_match_result(holes)
        assert mr.closed_at == 10
        assert mr.holes_played == 10

    def test_ignores_results_after_close(self) -> None:
        # Win holes 1-10, but also have results on 11-18
        # The match should close at hole 10 and ignore the rest
        holes = [_hole(i, "win") for i in range(1, 11)]
        holes += [_hole(i, "loss") for i in range(11, 19)]
        mr = compute_match_result(holes)
        assert mr.closed_at == 10
        assert mr.holes_played == 10
        assert mr.holes_won == 10
        assert mr.holes_lost == 0  # losses after close are ignored
