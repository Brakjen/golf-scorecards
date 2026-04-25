"""Pydantic models for persisted rounds and hole data."""

from datetime import date, datetime

from pydantic import BaseModel


class RoundHole(BaseModel):
    """A single hole's recorded data within a round.

    Stores both the static course snapshot data (par, distance, handicap)
    and the player's recorded metrics. Metric fields are ``None`` until
    the player transcribes their paper scorecard.

    Attributes:
        id: Unique identifier for this hole record.
        round_id: Foreign key to the parent round.
        hole_number: Hole number (1–18).
        par: Par for the hole (from course snapshot).
        distance: Playing distance in metres (from course snapshot).
        handicap: Stroke index for the hole (from course snapshot).
        score: Gross strokes taken on the hole.
        putts: Number of putts on the green.
        fir: Fairway in regulation (1 = hit, 0 = missed, ``None`` = N/A for par 3s).
        gir: Green in regulation (1 = hit, 0 = missed).
        penalty_strokes: Number of penalty strokes incurred.
        miss_direction: Direction of green miss ("left", "right", "short", "long").
        up_and_down: Whether the player got up-and-down (1 = yes, 0 = no).
        sand_save: Whether the player saved par from a bunker (1 = yes, 0 = no).
        sz_in_reg: Whether the player reached the scoring zone in regulation (1/0).
        down_in_3: Whether the player holed out in ≤3 from the scoring zone (1/0).
        putt_under_4ft: Whether a putt ≤4 ft was made (1 = made, 0 = missed).
        made_over_4ft: Whether a putt >4 ft was made (1 = made, 0 = missed).
        notes: Free-text notes for the hole.
    """

    id: str
    round_id: str
    hole_number: int
    par: int
    distance: int
    handicap: int
    score: int | None = None
    putts: int | None = None
    fir: int | None = None
    gir: int | None = None
    penalty_strokes: int | None = None
    miss_direction: str | None = None
    up_and_down: int | None = None
    sand_save: int | None = None
    sz_in_reg: int | None = None
    down_in_3: int | None = None
    putt_under_4ft: int | None = None
    made_over_4ft: int | None = None
    notes: str | None = None


class Round(BaseModel):
    """A persisted golf round with optional hole data.

    Captures the full context of a round including the player's handicap
    information, the course/slope ratings at the time of play, and a JSON
    snapshot of the course and tee data so that historical rounds remain
    accurate even if the catalog is later updated.

    Attributes:
        id: Unique identifier (hex UUID).
        course_slug: URL-safe course identifier from the catalog.
        tee_name: Selected tee name (e.g. "58", "63").
        player_name: Name of the golfer.
        round_date: Date the round was played.
        handicap_index: Player's WHS handicap index at time of play.
        handicap_profile: Gender profile used for handicap ("men" or "women").
        playing_handicap: Computed WHS playing handicap for this tee.
        course_rating: Course rating for the selected tee and profile.
        slope_rating: Slope rating for the selected tee and profile.
        scoring_mode: Scoring format ("stroke" or "stableford").
        target_score: Optional target score for stroke play.
        course_snapshot: JSON blob capturing course/tee/hole data at creation.
        created_at: Timestamp when the round was created.
        updated_at: Timestamp of the most recent hole data save.
        holes: Ordered list of hole records (empty metrics until transcribed).
    """

    id: str
    course_slug: str
    tee_name: str
    player_name: str | None = None
    round_date: date
    handicap_index: float | None = None
    handicap_profile: str | None = None
    playing_handicap: int | None = None
    course_rating: float | None = None
    slope_rating: int | None = None
    scoring_mode: str = "stroke"
    target_score: int | None = None
    course_snapshot: str
    created_at: datetime
    updated_at: datetime
    holes: list[RoundHole] = []


class RoundSummary(BaseModel):
    """Lightweight round summary for list views.

    Aggregated from the ``rounds`` and ``round_holes`` tables via SQL.
    Used on the landing page and round history list to avoid loading
    full hole-level data.

    Attributes:
        id: Round identifier.
        course_slug: URL-safe course identifier.
        tee_name: Selected tee name.
        player_name: Name of the golfer.
        round_date: Date the round was played.
        handicap_index: Player's handicap index at time of play.
        playing_handicap: Computed playing handicap for this tee.
        scoring_mode: Scoring format ("stroke" or "stableford").
        total_score: Sum of gross scores across all entered holes.
        total_putts: Sum of putts across all entered holes.
        gir_count: Number of greens hit in regulation.
        gir_total: Number of holes with GIR data entered.
        created_at: Timestamp when the round was created.
    """

    id: str
    course_slug: str
    tee_name: str
    player_name: str | None = None
    round_date: date
    handicap_index: float | None = None
    playing_handicap: int | None = None
    scoring_mode: str
    total_score: int | None = None
    total_putts: int | None = None
    gir_count: int | None = None
    gir_total: int | None = None
    created_at: datetime
