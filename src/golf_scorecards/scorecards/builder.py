"""Builder that assembles a printable scorecard from form data and course info."""

from golf_scorecards.catalog.models import Course, Hole, Tee
from golf_scorecards.handicap.models import HandicapComputation
from golf_scorecards.scorecards.forms import ScorecardFormData
from golf_scorecards.scorecards.models import (
    PrintableScorecard,
    ScorecardHoleRow,
    ScorecardMeta,
    ScorecardTotals,
)


class ScorecardBuilder:
    """Constructs a ``PrintableScorecard`` from user input and course data."""

    def build(
        self,
        form_data: ScorecardFormData,
        course: Course,
        tee: Tee | None = None,
        handicap: HandicapComputation | None = None,
    ) -> PrintableScorecard:
        """Build a complete scorecard.

        Args:
            form_data: Validated user form input.
            course: The selected course.
            tee: The selected tee box, or ``None`` for a course-only card.
            handicap: Optional WHS handicap computation result.

        Returns:
            A fully populated scorecard ready for rendering.
        """
        holes: list[Hole] = tee.holes[:18] if tee is not None else []
        if not holes and course.tees:
            holes = course.tees[0].holes[:18]
        course_par = sum(h.par for h in holes) if holes else 0
        if tee is not None and tee.par_total:
            course_par = tee.par_total

        is_stableford = form_data.scoring_mode == "stableford"
        show_adjusted_par = (
            form_data.scoring_mode == "stroke" and form_data.target_score is not None
        )
        show_stableford_columns = is_stableford
        adjusted_pars = self._build_adjusted_par_map(
            holes=holes,
            course_par=course_par,
            target_score=form_data.target_score if show_adjusted_par else None,
        )
        strokes_received = self._build_strokes_received_map(
            holes=holes,
            playing_strokes=(
                handicap.playing_handicap
                if handicap is not None
                else (0 if is_stableford else None)
            ),
        )
        two_point_targets = self._build_two_point_target_map(
            holes=holes,
            strokes_received=strokes_received,
            is_stableford=is_stableford,
        )

        all_holes = [
            self._build_row(
                hole,
                adjusted_par=adjusted_pars.get(hole.hole_number),
                strokes_received=strokes_received.get(hole.hole_number),
                two_points_score=two_point_targets.get(hole.hole_number),
                show_distance=tee is not None,
            )
            for hole in holes
        ]
        front_nine = all_holes[:9]
        back_nine = all_holes[9:18]

        front_totals = self._build_totals(front_nine)
        back_totals = self._build_totals(back_nine)

        return PrintableScorecard(
            meta=ScorecardMeta(
                player_name=form_data.player_name,
                round_date=form_data.round_date,
                club_name=course.club_name,
                course_name=course.course_name,
                course_slug=course.course_slug,
                tee_name=tee.tee_name if tee is not None else None,
                scoring_mode=self._format_scoring_mode(form_data.scoring_mode),
                target_score=form_data.target_score,
                handicap_index_label=self._format_handicap_index(form_data.handicap_index),
                handicap_index_raw=(
                    str(form_data.handicap_index) if form_data.handicap_index is not None else None
                ),
                handicap_profile_label=(
                    handicap.tee_rating.gender.capitalize()
                    if handicap is not None
                    else None
                ),
                handicap_profile_raw=form_data.handicap_profile,
                course_rating=(
                    handicap.tee_rating.course_rating if handicap is not None else None
                ),
                slope_rating=(
                    handicap.tee_rating.slope_rating if handicap is not None else None
                ),
                playing_strokes_total=(
                    handicap.playing_handicap if handicap is not None else None
                ),
            ),
            all_holes=all_holes,
            front_nine=front_nine,
            back_nine=back_nine,
            front_totals=front_totals,
            back_totals=back_totals,
            overall_totals=ScorecardTotals(
                par_total=front_totals.par_total + back_totals.par_total,
                distance_total=(
                    front_totals.distance_total + back_totals.distance_total
                    if front_totals.distance_total is not None
                    and back_totals.distance_total is not None
                    else None
                ),
                adjusted_par_total=(
                    front_totals.adjusted_par_total + back_totals.adjusted_par_total
                    if show_adjusted_par
                    and front_totals.adjusted_par_total is not None
                    and back_totals.adjusted_par_total is not None
                    else None
                ),
            ),
            main_columns=self._build_main_columns(
                scoring_mode=form_data.scoring_mode,
                show_adjusted_par=show_adjusted_par,
                show_stableford_columns=show_stableford_columns,
            ),
            show_adjusted_par=show_adjusted_par,
            show_stableford_columns=show_stableford_columns,
            summary_blank_colspan=self._build_summary_blank_colspan(
                scoring_mode=form_data.scoring_mode,
                show_adjusted_par=show_adjusted_par,
            ),
            scoring_zone_rule_label=(
                "Scoring-zone regulation uses the 2-point target minus 2."
                if is_stableford
                else (
                    "Scoring-zone regulation uses adjusted par minus 2."
                    if show_adjusted_par
                    else "Scoring-zone regulation uses par minus 2."
                )
            ),
        )

    def _build_main_columns(
        self,
        scoring_mode: str,
        show_adjusted_par: bool,
        show_stableford_columns: bool,
    ) -> list[str]:
        """Return the ordered column header list based on scoring mode."""
        columns = ["Hole", "HCP", "Par"]

        if show_adjusted_par:
            columns.append("Adjusted Par")

        columns.append("Distance")

        if show_stableford_columns and scoring_mode == "stableford":
            columns.extend(["Strokes"])

        columns.extend(
            [
                "Score",
            ]
        )

        if show_stableford_columns and scoring_mode == "stableford":
            columns.append("Pts")

        columns.extend(
            [
                "SZ in Reg",
                "Down in 3",
                "Green Miss",
                "Up and Down",
                "Putts",
                "NFS",
                "Pen",
            ]
        )

        return columns

    def _build_row(
        self,
        hole: Hole,
        adjusted_par: int | None,
        strokes_received: int | None,
        two_points_score: int | None,
        show_distance: bool = True,
    ) -> ScorecardHoleRow:
        """Create a single hole row for the scorecard table."""
        return ScorecardHoleRow(
            hole_number=hole.hole_number,
            handicap=hole.handicap,
            par=hole.par,
            adjusted_par=adjusted_par,
            distance=hole.distance if show_distance else None,
            strokes_received=strokes_received,
            two_points_score=two_points_score,
        )

    def _build_totals(self, holes: list[ScorecardHoleRow]) -> ScorecardTotals:
        """Aggregate par, distance, and adjusted par for a group of holes."""
        has_distance = any(hole.distance is not None for hole in holes)
        return ScorecardTotals(
            par_total=sum(hole.par for hole in holes),
            distance_total=(
                sum(hole.distance for hole in holes if hole.distance is not None)
                if has_distance
                else None
            ),
            adjusted_par_total=(
                sum(hole.adjusted_par for hole in holes if hole.adjusted_par is not None)
                if any(hole.adjusted_par is not None for hole in holes)
                else None
            ),
        )

    def _build_adjusted_par_map(
        self, holes: list[Hole], course_par: int, target_score: int | None
    ) -> dict[int, int]:
        """Distribute the target-score adjustment across holes by handicap.

        Extra strokes are assigned to holes with the lowest stroke index
        first (or removed from highest-index holes when target < par).
        """
        if target_score is None:
            return {}

        difference = target_score - course_par
        sign = 1 if difference >= 0 else -1
        base_adjustment, remainder = divmod(abs(difference), len(holes))

        adjusted_pars = {
            hole.hole_number: hole.par + (sign * base_adjustment)
            for hole in holes
        }

        prioritized_holes = sorted(
            holes,
            key=lambda hole: hole.handicap,
            reverse=sign < 0,
        )

        for hole in prioritized_holes[:remainder]:
            adjusted_pars[hole.hole_number] += sign

        return adjusted_pars

    def _build_strokes_received_map(
        self, holes: list[Hole], playing_strokes: int | None
    ) -> dict[int, int]:
        """Map each hole to the number of WHS strokes received."""
        if playing_strokes is None:
            return {}

        sign = 1 if playing_strokes >= 0 else -1
        base_strokes, remainder = divmod(abs(playing_strokes), len(holes))
        stroke_map = {
            hole.hole_number: sign * base_strokes
            for hole in holes
        }

        for hole in sorted(holes, key=lambda candidate: candidate.handicap)[:remainder]:
            stroke_map[hole.hole_number] += sign

        return stroke_map

    def _build_two_point_target_map(
        self,
        holes: list[Hole],
        strokes_received: dict[int, int],
        is_stableford: bool,
    ) -> dict[int, int]:
        """Compute the 2-point target score per hole for stableford."""
        if not is_stableford:
            return {}

        return {
            hole.hole_number: hole.par + strokes_received.get(hole.hole_number, 0)
            for hole in holes
        }

    def _build_summary_blank_colspan(self, scoring_mode: str, show_adjusted_par: bool) -> int:
        """Calculate the blank-cell colspan for summary rows."""
        used_columns = 4 + (1 if show_adjusted_par else 0)
        total_columns = len(
            self._build_main_columns(
                scoring_mode=scoring_mode,
                show_adjusted_par=show_adjusted_par,
                show_stableford_columns=scoring_mode == "stableford",
            )
        )
        return total_columns - used_columns

    def _format_scoring_mode(self, scoring_mode: str) -> str:
        """Return a human-readable scoring mode label."""
        if scoring_mode == "stableford":
            return "Stableford"
        return "Stroke play"

    def _format_handicap_index(self, handicap_index: float | None) -> str | None:
        """Format handicap index for display (prefix ``+`` for plus handicaps)."""
        if handicap_index is None:
            return None
        if handicap_index < 0:
            return f"+{abs(handicap_index):.1f}"
        return f"{handicap_index:.1f}"
