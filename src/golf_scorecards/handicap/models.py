"""Data models for handicap computation results."""

from pydantic import BaseModel, ConfigDict

from golf_scorecards.catalog.models import TeeRating


class HandicapComputation(BaseModel):
    """Result of computing playing handicap from the WHS formula.

    Attributes:
        tee_rating: The gender-specific course/slope rating used.
        handicap_index: The golfer's handicap index.
        playing_handicap: Computed playing handicap strokes.
    """

    model_config = ConfigDict(frozen=True)

    tee_rating: TeeRating
    handicap_index: float
    playing_handicap: int
