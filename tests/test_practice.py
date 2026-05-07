"""Tests for the practice module — models, stations, service, and repository."""

import tempfile
from datetime import date, datetime

import pytest

from golf_scorecards.db.connection import init_db_sync
from golf_scorecards.practice.models import (
    PracticeAttempt,
    PracticeSession,
    PracticeSessionSummary,
    Station,
)
from golf_scorecards.practice.repository import PracticeRepository
from golf_scorecards.practice.service import (
    PracticeService,
    PracticeSessionNotFoundError,
)
from golf_scorecards.practice.stations import STATIONS, get_station, station_order


# ── Station catalog tests ─────────────────────────────────────────────────


def test_station_catalog_has_seven_stations() -> None:
    assert len(STATIONS) == 7


def test_station_catalog_slugs_are_unique() -> None:
    slugs = [s.slug for s in STATIONS]
    assert len(slugs) == len(set(slugs))


def test_station_categories() -> None:
    categories = {s.category for s in STATIONS}
    assert categories == {"putt", "pitch", "bunker"}


def test_get_station_valid() -> None:
    s = get_station("putt-medium")
    assert s.name == "Putt 5–8m"
    assert s.category == "putt"


def test_get_station_invalid() -> None:
    with pytest.raises(KeyError):
        get_station("nonexistent")


def test_station_order_returns_all_slugs() -> None:
    order = station_order()
    assert len(order) == 7
    assert order[0] == "putt-short"
    assert order[-1] == "bunker"


# ── Model tests ───────────────────────────────────────────────────────────


def test_practice_attempt_defaults() -> None:
    a = PracticeAttempt(
        id="abc", session_id="sess1", station_slug="putt-medium",
        attempt_number=1, strokes=2,
    )
    assert a.nfs is False


def test_practice_session_defaults() -> None:
    s = PracticeSession(
        id="s1", session_date=date(2025, 1, 15), created_at=datetime(2025, 1, 15, 10, 0)
    )
    assert s.attempts == []
    assert s.notes is None


# ── Repository and service tests (async) ──────────────────────────────────


@pytest.fixture
def db_path(tmp_path):
    path = str(tmp_path / "test_practice.db")
    init_db_sync(path)
    return path


@pytest.fixture
def service(db_path):
    repo = PracticeRepository(db_path)
    return PracticeService(repo)


@pytest.mark.asyncio
async def test_create_session(service: PracticeService) -> None:
    session = await service.create_session("test-user", session_date=date(2025, 7, 1))
    assert session.id
    assert session.session_date == date(2025, 7, 1)
    assert session.attempts == []


@pytest.mark.asyncio
async def test_get_session(service: PracticeService) -> None:
    session = await service.create_session("test-user", session_date=date(2025, 7, 1))
    fetched = await service.get_session(session.id, "test-user")
    assert fetched.id == session.id
    assert fetched.session_date == date(2025, 7, 1)


@pytest.mark.asyncio
async def test_get_session_not_found(service: PracticeService) -> None:
    with pytest.raises(PracticeSessionNotFoundError):
        await service.get_session("nonexistent", "test-user")


@pytest.mark.asyncio
async def test_record_attempt(service: PracticeService) -> None:
    session = await service.create_session("test-user", session_date=date(2025, 7, 1))
    attempt = await service.record_attempt(
        session_id=session.id,
        station_slug="putt-medium",
        attempt_number=1,
        strokes=2,
    )
    assert attempt.strokes == 2
    assert attempt.station_slug == "putt-medium"

    fetched = await service.get_session(session.id, "test-user")
    assert len(fetched.attempts) == 1
    assert fetched.attempts[0].strokes == 2


@pytest.mark.asyncio
async def test_record_attempt_invalid_station(service: PracticeService) -> None:
    session = await service.create_session("test-user", )
    with pytest.raises(KeyError):
        await service.record_attempt(
            session_id=session.id,
            station_slug="invalid",
            attempt_number=1,
            strokes=3,
        )


@pytest.mark.asyncio
async def test_list_sessions(service: PracticeService) -> None:
    await service.create_session("test-user", session_date=date(2025, 7, 1))
    await service.create_session("test-user", session_date=date(2025, 7, 2))
    summaries = await service.list_sessions("test-user")
    assert len(summaries) == 2
    # Newest first
    assert summaries[0].session_date == date(2025, 7, 2)


@pytest.mark.asyncio
async def test_list_sessions_with_attempts(service: PracticeService) -> None:
    session = await service.create_session("test-user", session_date=date(2025, 7, 1))
    await service.record_attempt(session.id, "putt-medium", 1, strokes=2)
    await service.record_attempt(session.id, "putt-medium", 2, strokes=3)
    summaries = await service.list_sessions("test-user")
    assert summaries[0].total_strokes == 5
    assert summaries[0].total_attempts == 2


@pytest.mark.asyncio
async def test_delete_session(service: PracticeService) -> None:
    session = await service.create_session("test-user", )
    await service.record_attempt(session.id, "putt-medium", 1, strokes=2)
    await service.delete_session(session.id, "test-user")
    with pytest.raises(PracticeSessionNotFoundError):
        await service.get_session(session.id, "test-user")


@pytest.mark.asyncio
async def test_delete_session_not_found(service: PracticeService) -> None:
    with pytest.raises(PracticeSessionNotFoundError):
        await service.delete_session("nonexistent", "test-user")


# ── Stats tests ───────────────────────────────────────────────────────────


def test_compute_stats_empty(service: PracticeService) -> None:
    session = PracticeSession(
        id="s1", session_date=date(2025, 7, 1), created_at=datetime(2025, 7, 1, 10, 0)
    )
    stats = service.compute_stats(session)
    assert stats["total_strokes"] == 0
    assert stats["up_and_down_pct"] is None


def test_compute_stats_full_session(service: PracticeService) -> None:
    attempts = [
        PracticeAttempt(id=f"a{i}", session_id="s1", station_slug="putt-medium",
                        attempt_number=i, strokes=2)
        for i in range(1, 8)
    ] + [
        PracticeAttempt(id=f"b{i}", session_id="s1", station_slug="pitch-40",
                        attempt_number=i, strokes=3)
        for i in range(1, 8)
    ]
    session = PracticeSession(
        id="s1", session_date=date(2025, 7, 1),
        created_at=datetime(2025, 7, 1, 10, 0),
        attempts=attempts,
    )
    stats = service.compute_stats(session)
    # 7×2 + 7×3 = 14 + 21 = 35
    assert stats["total_strokes"] == 35
    assert stats["total_attempts"] == 14
    assert stats["avg_strokes"] == 2.5
    # U&D: 7 out of 14 (the putts all ≤2)
    assert stats["up_and_down_pct"] == 50.0
    # D3: all 14 are ≤3
    assert stats["down_in_3_pct"] == 100.0
    # Station breakdown
    assert stats["station_stats"]["putt-medium"]["avg_strokes"] == 2.0
    assert stats["station_stats"]["pitch-40"]["avg_strokes"] == 3.0
