"""Business logic for querying the course catalog."""

from typing import TypedDict

from golf_scorecards.catalog.models import Course, Tee
from golf_scorecards.catalog.repository import CourseCatalogRepository


class CourseOption(TypedDict):
    """Serialisable summary of a course for form dropdowns."""
    course_slug: str
    club_name: str
    course_name: str
    display_name: str
    tees: list[str]


class CatalogLookupError(ValueError):
    """Raised when a course catalog lookup fails."""


class CatalogService:
    """Read-only query interface for the in-memory course catalog."""

    def __init__(self, repository: CourseCatalogRepository) -> None:
        self._catalog = repository.load_catalog()

    def list_courses(self) -> list[Course]:
        """Return all courses in the catalog."""
        return list(self._catalog.courses)

    def get_course(self, course_slug: str) -> Course:
        """Look up a course by slug.

        Raises:
            CatalogLookupError: If the slug is not found.
        """
        for course in self._catalog.courses:
            if course.course_slug == course_slug:
                return course
        raise CatalogLookupError(f"Unknown course slug: {course_slug}")

    def get_tee(self, course_slug: str, tee_name: str) -> Tee:
        """Look up a specific tee on a course.

        Raises:
            CatalogLookupError: If the course or tee is not found.
        """
        course = self.get_course(course_slug)
        for tee in course.tees:
            if tee.tee_name == tee_name:
                return tee
        raise CatalogLookupError(f"Unknown tee '{tee_name}' for course '{course_slug}'")

    def list_course_options(self) -> list[CourseOption]:
        """Return lightweight course summaries for form dropdowns."""
        return [
            {
                "course_slug": course.course_slug,
                "club_name": course.club_name,
                "course_name": course.course_name,
                "display_name": f"{course.club_name} - {course.course_name}",
                "tees": [tee.tee_name for tee in course.tees],
            }
            for course in self._catalog.courses
        ]
