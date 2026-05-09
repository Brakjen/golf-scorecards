"""Tests for the insights service, serializer, and prompts."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from unittest.mock import AsyncMock

import pytest

from golf_scorecards.insights.prompts import SYSTEM_PROMPT, build_user_message
from golf_scorecards.insights.serializers import serialize_rounds
from golf_scorecards.insights.service import InsightsService
from golf_scorecards.rounds.models import Round, RoundHole
from golf_scorecards.rounds.stats import QuickStats, compute_quick_stats


def _make_hole(
    hole_number: int,
    par: int = 4,
    score: int | None = None,
    putts: int | None = None,
    **kwargs: object,
) -> RoundHole:
    return RoundHole(
        id=f"h{hole_number}",
        round_id="r1",
        hole_number=hole_number,
        par=par,
        distance=350,
        handicap=hole_number,
        score=score,
        putts=putts,
        **kwargs,
    )


def _make_round(
    round_id: str = "r1",
    holes: list[RoundHole] | None = None,
    round_date: date | None = None,
) -> Round:
    now = datetime.now(UTC)
    return Round(
        id=round_id,
        course_slug="test-course",
        tee_name="63",
        player_name="Test Player",
        round_date=round_date or date(2026, 4, 20),
        handicap_index=18.0,
        playing_handicap=20,
        course_rating=72.0,
        slope_rating=130,
        scoring_mode="stroke",
        holes_played="18",
        course_snapshot="{}",
        created_at=now,
        updated_at=now,
        holes=holes or [],
    )


# ── Serializer tests ────────────────────────────────────


class TestSerializeRounds:
    def test_empty_rounds(self) -> None:
        stats = QuickStats(
            rounds_count=0,
            avg_score=None,
            avg_putts=None,
            avg_penalties=None,
            up_and_down_pct=None,
        )
        result = serialize_rounds([], stats)
        assert "Rounds analysed: 0" in result

    def test_includes_aggregate_stats(self) -> None:
        stats = QuickStats(
            rounds_count=3,
            avg_score=85.0,
            avg_putts=32.0,
            avg_penalties=1.5,
            up_and_down_pct=40.0,
        )
        result = serialize_rounds([], stats)
        assert "Avg gross score: 85.0" in result
        assert "Avg putts/round: 32.0" in result
        assert "Scrambling (up-and-down): 40.0%" in result

    def test_includes_round_detail(self) -> None:
        holes = [
            _make_hole(1, par=4, score=5, putts=2, miss_direction="left"),
            _make_hole(2, par=3, score=3, putts=1),
        ]
        r = _make_round(holes=holes)
        stats = compute_quick_stats([r])
        result = serialize_rounds([r], stats)
        assert "Test Course" in result
        assert "Score: 8 (par 7, +1)" in result
        assert "Green misses: left 1" in result
        assert "H1 | P4 | S5(+1) | Pt2 | Miss:left" in result
        assert "H2 | P3 | S3(E) | Pt1" in result

    def test_includes_nfs_and_penalties(self) -> None:
        holes = [_make_hole(1, score=7, putts=2, nfs=2, penalty_strokes=1)]
        r = _make_round(holes=holes)
        stats = compute_quick_stats([r])
        result = serialize_rounds([r], stats)
        assert "Non-functional strikes: 2" in result
        assert "Penalty strokes: 1" in result

    def test_relative_scoring(self) -> None:
        from golf_scorecards.insights.serializers import _relative

        assert _relative(0) == "E"
        assert _relative(3) == "+3"
        assert _relative(-2) == "-2"


# ── Prompts tests ────────────────────────────────────────


class TestPrompts:
    def test_system_prompt_has_json_instruction(self) -> None:
        assert "JSON array" in SYSTEM_PROMPT
        assert "exactly 3" in SYSTEM_PROMPT

    def test_build_user_message(self) -> None:
        msg = build_user_message("some round data")
        assert "some round data" in msg
        assert "coaching insights" in msg.lower()


# ── Service tests ────────────────────────────────────────


class TestParseResponse:
    def test_valid_json_array(self) -> None:
        content = json.dumps(["Insight 1", "Insight 2", "Insight 3"])
        result = InsightsService._parse_response(content)
        assert result == ["Insight 1", "Insight 2", "Insight 3"]

    def test_strips_markdown_fences(self) -> None:
        content = '```json\n["Insight 1", "Insight 2"]\n```'
        result = InsightsService._parse_response(content)
        assert result == ["Insight 1", "Insight 2"]

    def test_rejects_non_array(self) -> None:
        with pytest.raises(ValueError, match="JSON array"):
            InsightsService._parse_response('{"key": "value"}')

    def test_rejects_non_string_array(self) -> None:
        with pytest.raises(ValueError, match="JSON array"):
            InsightsService._parse_response("[1, 2, 3]")

    def test_rejects_invalid_json(self) -> None:
        with pytest.raises(json.JSONDecodeError):
            InsightsService._parse_response("not json at all")


class TestHashRounds:
    def test_same_rounds_same_hash(self) -> None:
        r1 = _make_round("a")
        r2 = _make_round("b")
        hash1 = InsightsService._hash_rounds([r1, r2])
        hash2 = InsightsService._hash_rounds([r2, r1])  # reversed order
        assert hash1 == hash2

    def test_different_rounds_different_hash(self) -> None:
        r1 = _make_round("a")
        r2 = _make_round("c")
        hash1 = InsightsService._hash_rounds([r1])
        hash2 = InsightsService._hash_rounds([r2])
        assert hash1 != hash2


class TestGenerateInsights:
    @pytest.mark.asyncio
    async def test_returns_cached_if_available(self) -> None:
        service = InsightsService.__new__(InsightsService)
        service._db_path = ":memory:"
        service._model = "gpt-4o"

        cached = ["cached insight 1", "cached insight 2"]
        service._read_cache = AsyncMock(return_value=cached)
        service._call_openai = AsyncMock()

        r = _make_round()
        result = await service.generate_insights([r])

        assert result == cached
        service._call_openai.assert_not_called()

    @pytest.mark.asyncio
    async def test_calls_openai_on_cache_miss(self) -> None:
        service = InsightsService.__new__(InsightsService)
        service._db_path = ":memory:"
        service._model = "gpt-4o"

        fresh = ["fresh insight 1", "fresh insight 2"]
        service._read_cache = AsyncMock(return_value=None)
        service._call_openai = AsyncMock(return_value=fresh)
        service._write_cache = AsyncMock()

        holes = [_make_hole(1, score=5, putts=2)]
        r = _make_round(holes=holes)
        result = await service.generate_insights([r])

        assert result == fresh
        service._call_openai.assert_called_once()
        service._write_cache.assert_called_once()

    @pytest.mark.asyncio
    async def test_empty_rounds_returns_empty(self) -> None:
        service = InsightsService.__new__(InsightsService)
        service._db_path = ":memory:"
        result = await service.generate_insights([])
        assert result == []

    @pytest.mark.asyncio
    async def test_cache_key_passed_to_read_and_write(self) -> None:
        service = InsightsService.__new__(InsightsService)
        service._db_path = ":memory:"
        service._model = "gpt-4o"

        fresh = ["a", "b", "c"]
        service._read_cache = AsyncMock(return_value=None)
        service._call_openai = AsyncMock(return_value=fresh)
        service._write_cache = AsyncMock()

        r = _make_round("xyz", holes=[_make_hole(1, score=5, putts=2)])
        result = await service.generate_insights([r], cache_key="round:xyz")

        assert result == fresh
        # read_cache called with the round-scoped key
        read_args = service._read_cache.call_args
        assert read_args.args[0] == "round:xyz"
        # write_cache called with the round-scoped key
        write_args = service._write_cache.call_args
        assert write_args.args[0] == "round:xyz"
        assert write_args.args[2] == fresh


class TestAnswerQuestion:
    @pytest.mark.asyncio
    async def test_calls_openai_and_returns_entry(self) -> None:
        service = InsightsService.__new__(InsightsService)
        service._db_path = ":memory:"
        service._model = "gpt-4o"

        service._call_openai_qa = AsyncMock(return_value="Work on putting.")

        r = _make_round(holes=[_make_hole(1, score=4, putts=2)])
        result = await service.answer_question(
            [r], "Where am I losing strokes?",
        )

        assert result.question == "Where am I losing strokes?"
        assert result.answer == "Work on putting."
        service._call_openai_qa.assert_called_once()

    @pytest.mark.asyncio
    async def test_empty_question_raises(self) -> None:
        service = InsightsService.__new__(InsightsService)
        service._db_path = ":memory:"
        r = _make_round(holes=[_make_hole(1, score=4)])
        with pytest.raises(ValueError, match="empty"):
            await service.answer_question([r], "   ")

    @pytest.mark.asyncio
    async def test_empty_rounds_raises(self) -> None:
        service = InsightsService.__new__(InsightsService)
        service._db_path = ":memory:"
        with pytest.raises(ValueError, match="No rounds"):
            await service.answer_question([], "Anything?")

    @pytest.mark.asyncio
    async def test_question_is_stripped(self) -> None:
        service = InsightsService.__new__(InsightsService)
        service._db_path = ":memory:"
        service._model = "gpt-4o"

        service._call_openai_qa = AsyncMock(return_value="Answer.")

        r = _make_round(holes=[_make_hole(1, score=4)])
        result = await service.answer_question([r], "  hello?  ")
        assert result.question == "hello?"
