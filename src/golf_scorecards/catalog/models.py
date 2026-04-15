"""Pydantic models for the golf course catalog."""

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class Hole(BaseModel):
    """A single hole on a golf course.

    Attributes:
        hole_number: Hole number (1-18).
        par: Par for the hole.
        distance: Playing distance in meters.
        handicap: Stroke index for the hole.
    """
    model_config = ConfigDict(frozen=True)

    hole_number: int
    par: int
    distance: int
    handicap: int


class TeeRating(BaseModel):
    """Gender-specific course and slope rating for a tee.

    Attributes:
        gender: Rating category (e.g. ``"men"``, ``"women"``).
        course_rating: Course rating value.
        slope_rating: Slope rating value.
    """

    model_config = ConfigDict(frozen=True)

    gender: str
    course_rating: float
    slope_rating: int


class Tee(BaseModel):
    """A tee box with its holes and optional ratings.

    Attributes:
        tee_name: Display name for the tee (e.g. ``"58"``, ``"63"``).
        tee_category: Category label (e.g. colour or distance).
        gender_category: Optional gender restriction.
        number_of_holes: Number of holes for this tee.
        par_total: Total par across all holes.
        total_distance: Sum of hole distances in meters.
        ratings: Gender-specific course/slope ratings.
        holes: Ordered list of holes.
    """

    model_config = ConfigDict(frozen=True)

    tee_name: str
    tee_category: str
    gender_category: str | None = None
    number_of_holes: int
    par_total: int | None = None
    total_distance: int | None = Field(
        default=None,
        validation_alias=AliasChoices("total_distance", "total_yards"),
    )
    ratings: list[TeeRating] = []
    holes: list[Hole]


class Course(BaseModel):
    """A golf course belonging to a club.

    Attributes:
        club_name: Name of the golf club.
        course_name: Name of the specific course.
        course_slug: URL-safe identifier.
        tees: Available tee boxes.
    """

    model_config = ConfigDict(frozen=True)

    club_name: str
    course_name: str
    course_slug: str
    tees: list[Tee]


class CourseCatalog(BaseModel):
    """Top-level container for the packaged course catalog.

    Attributes:
        schema_version: Catalog schema version string.
        dataset: Dataset identifier.
        source: Data source descriptor.
        country_code: ISO country code for the catalog.
        courses: All courses in the catalog.
    """

    model_config = ConfigDict(frozen=True)

    schema_version: str
    dataset: str
    source: str
    country_code: str
    courses: list[Course]
