"""Form validation and parsing for scorecard creation."""

from datetime import date
from typing import Annotated

from fastapi import Form
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ScorecardFormData(BaseModel):
    """Validated scorecard creation form data.

    Attributes:
        player_name: Name of the golfer.
        round_date: Date of the round.
        course_slug: URL-safe course identifier.
        tee_name: Selected tee name.
        scoring_mode: ``"stroke"`` or ``"stableford"``.
        target_score: Optional target score (stroke play only).
        handicap_index: Optional WHS handicap index.
        handicap_profile: Optional gender profile key.
    """
    model_config = ConfigDict(str_strip_whitespace=True)

    player_name: str | None = Field(default=None, max_length=100)
    round_date: date | None = None
    course_slug: str = Field(min_length=1)
    tee_name: str | None = None
    scoring_mode: str = Field(default="stroke")
    target_score: int | None = Field(default=None, ge=1, le=200)
    handicap_index: float | None = None
    handicap_profile: str | None = None

    @field_validator("player_name", "tee_name", mode="before")
    @classmethod
    def blank_to_none(cls, value: object) -> object:
        """Treat empty strings as ``None``."""
        if value in (None, ""):
            return None
        return value

    @field_validator("round_date", mode="before")
    @classmethod
    def blank_round_date_to_none(cls, value: object) -> object:
        """Treat empty strings as ``None``."""
        if value in (None, ""):
            return None
        return value

    @field_validator("scoring_mode", mode="before")
    @classmethod
    def normalize_scoring_mode(cls, value: object) -> str:
        """Coerce blank/alias values to canonical scoring mode."""
        if value in (None, ""):
            return "stroke"

        normalized = str(value).strip().lower()
        aliases = {
            "stroke": "stroke",
            "stroke-play": "stroke",
            "stroke play": "stroke",
            "stableford": "stableford",
        }
        if normalized not in aliases:
            raise ValueError("Scoring mode must be stroke or stableford")
        return aliases[normalized]

    @field_validator("target_score", mode="before")
    @classmethod
    def blank_target_score_to_none(cls, value: object) -> object:
        """Treat empty strings as ``None``."""
        if value in (None, ""):
            return None
        return value

    @field_validator("handicap_index", mode="before")
    @classmethod
    def parse_handicap_index(cls, value: object) -> object:
        """Parse handicap index from string, supporting ``+`` prefix for plus handicaps."""
        if value in (None, ""):
            return None
        if isinstance(value, int | float):
            return float(value)

        text = str(value).strip().replace(",", ".")
        if text.startswith("+"):
            return -float(text[1:])
        return float(text)

    @field_validator("handicap_profile", mode="before")
    @classmethod
    def normalize_handicap_profile(cls, value: object) -> object:
        """Normalise profile to ``men`` or ``women``, accepting Norwegian aliases."""
        if value in (None, ""):
            return None

        normalized = str(value).strip().lower()
        aliases = {"men": "men", "women": "women", "herrer": "men", "damer": "women"}
        if normalized not in aliases:
            raise ValueError("Handicap profile must be men or women")
        return aliases[normalized]

    @model_validator(mode="after")
    def apply_scoring_mode_rules(self) -> "ScorecardFormData":
        """Clear target score when stableford mode is selected."""
        if self.scoring_mode == "stableford":
            self.target_score = None
        return self


async def parse_scorecard_form(
    course_slug: Annotated[str, Form(...)],
    player_name: Annotated[str | None, Form()] = None,
    tee_name: Annotated[str | None, Form()] = None,
    round_date: Annotated[date | None, Form()] = None,
    scoring_mode: Annotated[str, Form(...)] = "stroke",
    target_score: Annotated[str | None, Form()] = None,
    handicap_index: Annotated[str | None, Form()] = None,
    handicap_profile: Annotated[str | None, Form()] = None,
) -> ScorecardFormData:
    """FastAPI dependency that parses and validates the scorecard form."""
    return ScorecardFormData.model_validate(
        {
            "player_name": player_name,
            "round_date": round_date,
            "course_slug": course_slug,
            "tee_name": tee_name,
            "scoring_mode": scoring_mode,
            "target_score": target_score,
            "handicap_index": handicap_index,
            "handicap_profile": handicap_profile,
        }
    )
