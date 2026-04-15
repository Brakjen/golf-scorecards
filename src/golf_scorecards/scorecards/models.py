"""View models for the printable scorecard layout."""

from datetime import date

from pydantic import BaseModel, ConfigDict


class ScorecardMeta(BaseModel):
    """Header metadata displayed on the scorecard.

    Attributes:
        player_name: Name of the golfer.
        round_date: Date of the round.
        club_name: Golf club name.
        course_name: Course name.
        course_slug: URL-safe course identifier.
        tee_name: Selected tee name.
        scoring_mode: Display label for scoring mode.
        target_score: Optional target score for stroke play.
        handicap_index_label: Formatted handicap index label.
        handicap_index_raw: Raw handicap index string.
        handicap_profile_label: Formatted handicap profile label.
        handicap_profile_raw: Raw handicap profile key.
        course_rating: Course rating for the selected tee/profile.
        slope_rating: Slope rating for the selected tee/profile.
        playing_strokes_total: Computed WHS playing handicap.
    """
    model_config = ConfigDict(frozen=True)

    player_name: str | None = None
    round_date: date | None = None
    club_name: str
    course_name: str
    course_slug: str
    tee_name: str | None = None
    scoring_mode: str
    target_score: int | None = None
    handicap_index_label: str | None = None
    handicap_index_raw: str | None = None
    handicap_profile_label: str | None = None
    handicap_profile_raw: str | None = None
    course_rating: float | None = None
    slope_rating: int | None = None
    playing_strokes_total: int | None = None


class ScorecardHoleRow(BaseModel):
    """Per-hole data row rendered in the scorecard table.

    Attributes:
        hole_number: Hole number (1-18).
        handicap: Stroke index.
        par: Par for the hole.
        adjusted_par: Adjusted par when a target score is set.
        distance: Playing distance in meters.
        strokes_received: WHS strokes received on this hole.
        two_points_score: Stableford 2-point target score.
    """
    model_config = ConfigDict(frozen=True)

    hole_number: int
    handicap: int
    par: int
    adjusted_par: int | None = None
    distance: int | None = None
    strokes_received: int | None = None
    two_points_score: int | None = None


class ScorecardTotals(BaseModel):
    """Aggregated totals for a group of holes (front 9, back 9, or overall).

    Attributes:
        par_total: Sum of par values.
        distance_total: Sum of distances.
        adjusted_par_total: Sum of adjusted pars, if applicable.
    """
    model_config = ConfigDict(frozen=True)

    par_total: int
    distance_total: int | None = None
    adjusted_par_total: int | None = None


class PrintableScorecard(BaseModel):
    """Complete scorecard ready for template rendering.

    Attributes:
        meta: Scorecard header metadata.
        all_holes: All 18 hole rows.
        front_nine: Holes 1-9.
        back_nine: Holes 10-18.
        front_totals: Front nine aggregates.
        back_totals: Back nine aggregates.
        overall_totals: Full round aggregates.
        main_columns: Ordered column headers for the table.
        show_adjusted_par: Whether to render the adjusted par column.
        show_stableford_columns: Whether to render stableford columns.
        summary_blank_colspan: Colspan for blank cells in summary rows.
        scoring_zone_rule_label: Explanatory label for scoring-zone rule.
    """
    model_config = ConfigDict(frozen=True)

    meta: ScorecardMeta
    all_holes: list[ScorecardHoleRow]
    front_nine: list[ScorecardHoleRow]
    back_nine: list[ScorecardHoleRow]
    front_totals: ScorecardTotals
    back_totals: ScorecardTotals
    overall_totals: ScorecardTotals
    main_columns: list[str]
    show_adjusted_par: bool
    show_stableford_columns: bool
    summary_blank_colspan: int
    scoring_zone_rule_label: str
