"""Legacy helper functions for loading course data."""

from typing import Any

from golf_scorecards.catalog.repository import CourseCatalogRepository


def get_home_courses_path() -> str:
    """Return the filesystem path to the bundled course catalog JSON."""
    return CourseCatalogRepository().get_catalog_path()


def load_home_courses() -> dict[str, Any]:
    """Load the course catalog as a raw dictionary."""
    return CourseCatalogRepository().load_raw_catalog()
