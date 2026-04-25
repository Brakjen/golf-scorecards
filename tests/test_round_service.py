"""Tests for round service CRUD operations."""

import asyncio
from datetime import date

import pytest

from golf_scorecards.catalog.repository import CourseCatalogRepository
from golf_scorecards.catalog.service import CatalogService
from golf_scorecards.db.connection import init_db_sync
from golf_scorecards.rounds.models import RoundHole
from golf_scorecards.rounds.repository import RoundRepository
from golf_scorecards.rounds.service import RoundNotFoundError, RoundService


@pytest.fixture()
def db_path(tmp_path: object) -> str:
    """Create a temporary SQLite database."""
    path = str(tmp_path) + "/test.db"  # type: ignore[operator]
    init_db_sync(path)
    return path


@pytest.fixture()
def round_service(db_path: str) -> RoundService:
    return RoundService(repository=RoundRepository(db_path=db_path))


@pytest.fixture()
def catalog_service() -> CatalogService:
    return CatalogService(repository=CourseCatalogRepository())


def test_create_round(
    round_service: RoundService, catalog_service: CatalogService,
) -> None:
    """A new round should have 18 empty hole rows from the course snapshot."""
    course = catalog_service.get_course("sola-golfklubb-forus")
    tee = catalog_service.get_tee("sola-golfklubb-forus", "58")

    r = asyncio.get_event_loop().run_until_complete(
        round_service.create_round(
            course=course,
            tee=tee,
            round_date=date(2026, 4, 25),
            player_name="Test Player",
            scoring_mode="stroke",
        )
    )

    assert r.course_slug == "sola-golfklubb-forus"
    assert r.tee_name == "58"
    assert r.player_name == "Test Player"
    assert len(r.holes) == 18
    assert all(h.score is None for h in r.holes)
    assert r.holes[0].par == tee.holes[0].par


def test_get_round(
    round_service: RoundService, catalog_service: CatalogService,
) -> None:
    """A created round can be retrieved by ID."""
    course = catalog_service.get_course("sola-golfklubb-forus")
    tee = catalog_service.get_tee("sola-golfklubb-forus", "58")

    created = asyncio.get_event_loop().run_until_complete(
        round_service.create_round(
            course=course, tee=tee, round_date=date(2026, 4, 25),
        )
    )

    fetched = asyncio.get_event_loop().run_until_complete(
        round_service.get_round(created.id)
    )

    assert fetched.id == created.id
    assert fetched.course_slug == "sola-golfklubb-forus"
    assert len(fetched.holes) == 18


def test_get_round_not_found(round_service: RoundService) -> None:
    """Getting a non-existent round raises RoundNotFoundError."""
    with pytest.raises(RoundNotFoundError):
        asyncio.get_event_loop().run_until_complete(
            round_service.get_round("nonexistent")
        )


def test_save_holes(
    round_service: RoundService, catalog_service: CatalogService,
) -> None:
    """Saving hole data persists scores and metrics."""
    course = catalog_service.get_course("sola-golfklubb-forus")
    tee = catalog_service.get_tee("sola-golfklubb-forus", "58")

    created = asyncio.get_event_loop().run_until_complete(
        round_service.create_round(
            course=course, tee=tee, round_date=date(2026, 4, 25),
        )
    )

    updated_holes = [
        RoundHole(
            id=h.id,
            round_id=h.round_id,
            hole_number=h.hole_number,
            par=h.par,
            distance=h.distance,
            handicap=h.handicap,
            score=h.par + 1,
            putts=2,
            fir=1 if h.par > 3 else None,
            gir=0,
        )
        for h in created.holes
    ]

    updated = asyncio.get_event_loop().run_until_complete(
        round_service.save_holes(created.id, updated_holes)
    )

    assert updated.holes[0].score == updated.holes[0].par + 1
    assert updated.holes[0].putts == 2
    assert all(h.score is not None for h in updated.holes)


def test_list_rounds(
    round_service: RoundService, catalog_service: CatalogService,
) -> None:
    """Listing rounds returns summaries with aggregated scores."""
    course = catalog_service.get_course("sola-golfklubb-forus")
    tee = catalog_service.get_tee("sola-golfklubb-forus", "58")

    created = asyncio.get_event_loop().run_until_complete(
        round_service.create_round(
            course=course, tee=tee, round_date=date(2026, 4, 25),
        )
    )

    # Save some scores so we get non-null totals
    holes_with_scores = [
        RoundHole(
            id=h.id, round_id=h.round_id, hole_number=h.hole_number,
            par=h.par, distance=h.distance, handicap=h.handicap,
            score=4, putts=2, gir=1,
        )
        for h in created.holes
    ]
    asyncio.get_event_loop().run_until_complete(
        round_service.save_holes(created.id, holes_with_scores)
    )

    summaries = asyncio.get_event_loop().run_until_complete(
        round_service.list_rounds()
    )

    assert len(summaries) == 1
    assert summaries[0].id == created.id
    assert summaries[0].total_score == 72  # 18 holes × 4
    assert summaries[0].total_putts == 36  # 18 holes × 2
    assert summaries[0].gir_count == 18


def test_delete_round(
    round_service: RoundService, catalog_service: CatalogService,
) -> None:
    """Deleting a round removes it and its holes."""
    course = catalog_service.get_course("sola-golfklubb-forus")
    tee = catalog_service.get_tee("sola-golfklubb-forus", "58")

    created = asyncio.get_event_loop().run_until_complete(
        round_service.create_round(
            course=course, tee=tee, round_date=date(2026, 4, 25),
        )
    )

    asyncio.get_event_loop().run_until_complete(
        round_service.delete_round(created.id)
    )

    with pytest.raises(RoundNotFoundError):
        asyncio.get_event_loop().run_until_complete(
            round_service.get_round(created.id)
        )


def test_delete_round_not_found(round_service: RoundService) -> None:
    """Deleting a non-existent round raises RoundNotFoundError."""
    with pytest.raises(RoundNotFoundError):
        asyncio.get_event_loop().run_until_complete(
            round_service.delete_round("nonexistent")
        )


def test_create_front_9_round(
    round_service: RoundService, catalog_service: CatalogService,
) -> None:
    """A front-9 round should have only holes 1–9."""
    course = catalog_service.get_course("sola-golfklubb-forus")
    tee = catalog_service.get_tee("sola-golfklubb-forus", "58")

    r = asyncio.get_event_loop().run_until_complete(
        round_service.create_round(
            course=course, tee=tee, round_date=date(2026, 4, 25),
            holes_played="front_9",
        )
    )

    assert r.holes_played == "front_9"
    assert len(r.holes) == 9
    assert r.holes[0].hole_number == 1
    assert r.holes[-1].hole_number == 9


def test_create_back_9_round(
    round_service: RoundService, catalog_service: CatalogService,
) -> None:
    """A back-9 round should have only holes 10–18."""
    course = catalog_service.get_course("sola-golfklubb-forus")
    tee = catalog_service.get_tee("sola-golfklubb-forus", "58")

    r = asyncio.get_event_loop().run_until_complete(
        round_service.create_round(
            course=course, tee=tee, round_date=date(2026, 4, 25),
            holes_played="back_9",
        )
    )

    assert r.holes_played == "back_9"
    assert len(r.holes) == 9
    assert r.holes[0].hole_number == 10
    assert r.holes[-1].hole_number == 18
