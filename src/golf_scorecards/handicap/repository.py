"""Repository that reads slope/course-rating data from the course catalog."""

from golf_scorecards.catalog.models import Tee, TeeRating
from golf_scorecards.catalog.service import CatalogService


class SlopeRatingsRepository:
    """Reads slope/course-rating data from the consolidated course catalog."""

    def __init__(self, catalog_service: CatalogService) -> None:
        self._catalog = catalog_service

    def _get_tee(self, course_slug: str, tee_name: str) -> Tee | None:
        """Return the tee or ``None`` if not found."""
        try:
            return self._catalog.get_tee(course_slug, tee_name)
        except Exception:
            return None

    def get_rating(
        self, course_slug: str, tee_name: str, gender: str
    ) -> TeeRating | None:
        """Return the rating for a specific gender, or ``None`` if unavailable."""
        tee = self._get_tee(course_slug, tee_name)
        if tee is None:
            return None
        for rating in tee.ratings:
            if rating.gender == gender:
                return rating
        return None

    def get_par(self, course_slug: str, tee_name: str) -> int | None:
        """Return the total par for the tee, or ``None`` if not found."""
        tee = self._get_tee(course_slug, tee_name)
        return tee.par_total if tee is not None else None

    def has_ratings(self, course_slug: str, tee_name: str) -> bool:
        """Check whether the tee has at least one rating entry."""
        tee = self._get_tee(course_slug, tee_name)
        return tee is not None and len(tee.ratings) > 0

    def list_available_genders(
        self, course_slug: str, tee_name: str
    ) -> list[str]:
        """Return all gender keys that have ratings for the given tee."""
        tee = self._get_tee(course_slug, tee_name)
        if tee is None:
            return []
        return [r.gender for r in tee.ratings]
