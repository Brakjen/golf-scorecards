"""WHS playing-handicap computation service."""

from golf_scorecards.catalog.models import TeeRating
from golf_scorecards.handicap.models import HandicapComputation
from golf_scorecards.handicap.repository import SlopeRatingsRepository


class HandicapLookupError(ValueError):
    """Raised when handicap or slope-table data cannot be resolved."""


class HandicapService:
    """Computes playing handicap using the WHS formula and packaged slope data."""

    def __init__(self, repository: SlopeRatingsRepository) -> None:
        self._repository = repository

    def list_profile_options(
        self, course_slug: str, tee_name: str
    ) -> list[dict[str, str]]:
        """Return available handicap profile options for a tee."""
        genders = self._repository.list_available_genders(course_slug, tee_name)
        return [
            {"key": g, "label": g.capitalize()} for g in genders
        ]

    def get_rating(
        self, course_slug: str, tee_name: str, profile_key: str
    ) -> TeeRating:
        """Look up a tee rating by course, tee, and gender.

        Raises:
            HandicapLookupError: If the rating is not found.
        """
        rating = self._repository.get_rating(course_slug, tee_name, profile_key)
        if rating is None:
            raise HandicapLookupError(
                f"No slope data for course='{course_slug}', "
                f"tee='{tee_name}', gender='{profile_key}'"
            )
        return rating

    def has_ratings(self, course_slug: str, tee_name: str) -> bool:
        """Check whether slope data exists for the given tee."""
        return self._repository.has_ratings(course_slug, tee_name)

    def compute_playing_handicap(
        self,
        course_slug: str,
        tee_name: str,
        profile_key: str,
        handicap_index: float,
    ) -> HandicapComputation:
        """Compute the WHS playing handicap.

        Formula: ``round(HI * (Slope / 113) + (CR - Par))``

        Raises:
            HandicapLookupError: If rating or par data is missing.
        """
        rating = self.get_rating(course_slug, tee_name, profile_key)
        par = self._repository.get_par(course_slug, tee_name)
        if par is None:
            raise HandicapLookupError(
                f"No par data for course='{course_slug}', tee='{tee_name}'"
            )
        playing_handicap = round(
            handicap_index * (rating.slope_rating / 113)
            + (rating.course_rating - par)
        )
        return HandicapComputation(
            tee_rating=rating,
            handicap_index=handicap_index,
            playing_handicap=playing_handicap,
        )
