"""Tests for handicap computation using Forus and Stavanger course data."""

from golf_scorecards.catalog.repository import CourseCatalogRepository
from golf_scorecards.catalog.service import CatalogService
from golf_scorecards.handicap.repository import SlopeRatingsRepository
from golf_scorecards.handicap.service import HandicapService


def _make_service() -> HandicapService:
    catalog_service = CatalogService(repository=CourseCatalogRepository())
    return HandicapService(repository=SlopeRatingsRepository(catalog_service=catalog_service))


def test_slope_ratings_load_forus_tee() -> None:
    service = _make_service()

    rating = service.get_rating("sola-golfklubb-forus", "58", "men")

    assert rating.course_rating == 70.6
    assert rating.slope_rating == 139


def test_handicap_computation_uses_whs_formula() -> None:
    service = _make_service()

    result = service.compute_playing_handicap(
        course_slug="sola-golfklubb-forus",
        tee_name="58",
        profile_key="men",
        handicap_index=18.4,
    )

    # WHS: round(18.4 * (139 / 113) + (70.6 - 72)) = round(22.24 - 1.4) = round(21.24) = 21
    assert result.playing_handicap == 21
    assert result.tee_rating.gender == "men"


def test_handicap_computation_stavanger() -> None:
    service = _make_service()

    result = service.compute_playing_handicap(
        course_slug="stavanger-golfklubb",
        tee_name="58",
        profile_key="men",
        handicap_index=18.4,
    )

    # WHS: round(18.4 * (137 / 113) + (71.3 - 71)) = round(22.31 + 0.3) = round(22.61) = 23
    assert result.playing_handicap == 23