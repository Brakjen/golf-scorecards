"""Tests for catalog repository and service."""

from golf_scorecards.catalog.models import CourseCatalog
from golf_scorecards.catalog.repository import CourseCatalogRepository
from golf_scorecards.catalog.service import CatalogService


def test_repository_loads_typed_catalog() -> None:
    catalog = CourseCatalogRepository().load_catalog()

    assert isinstance(catalog, CourseCatalog)
    assert catalog.country_code == "NO"
    assert len(catalog.courses) == 6


def test_catalog_service_returns_course_and_tee() -> None:
    service = CatalogService(repository=CourseCatalogRepository())

    course = service.get_course("sola-golfklubb-forus")
    tee = service.get_tee("sola-golfklubb-forus", "63")

    assert course.course_name == "Forus"
    assert tee.tee_name == "63"
    assert tee.holes[0].distance == 330
