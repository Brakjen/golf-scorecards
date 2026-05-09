"""Match play scoring utilities.

Pure functions — no I/O or database access.
"""

from __future__ import annotations

from dataclasses import dataclass

from golf_scorecards.rounds.models import RoundHole


@dataclass(frozen=True)
class MatchResult:
    """Computed match play result.

    Attributes:
        holes_won: Number of holes won by the player.
        holes_lost: Number of holes lost by the player.
        holes_halved: Number of holes halved.
        holes_played: Number of holes with a recorded result.
        total_holes: Total holes in the round.
        result_text: Human-readable result, e.g. "W 3&2", "L 1 DN", "AS".
        is_complete: Whether the match is decided (dormie or finished).
        closed_at: Hole number where the match was decided (None if not).
        hole_status: Per-hole running status, e.g. {1: "1 UP", 2: "AS", ...}.
    """

    holes_won: int
    holes_lost: int
    holes_halved: int
    holes_played: int
    total_holes: int
    result_text: str
    is_complete: bool
    closed_at: int | None = None
    hole_status: dict[int, str] | None = None


def compute_match_result(holes: list[RoundHole]) -> MatchResult:
    """Compute the match play result from hole results.

    The match closes when a player's lead exceeds the number of
    remaining holes (the trailing player cannot catch up).  Results
    after the closing hole are ignored.

    Args:
        holes: Round holes sorted by hole_number, each with an optional
            ``hole_result`` of ``"win"``, ``"loss"``, or ``"halve"``.

    Returns:
        A ``MatchResult`` with the current or final match state.
    """
    total = len(holes)
    sorted_holes = sorted(holes, key=lambda h: h.hole_number)

    won = 0
    lost = 0
    halved = 0
    lead = 0
    closed_at: int | None = None
    hole_status: dict[int, str] = {}

    for h in sorted_holes:
        if h.hole_result is None:
            continue

        if h.hole_result == "win":
            won += 1
            lead += 1
        elif h.hole_result == "loss":
            lost += 1
            lead -= 1
        elif h.hole_result == "halve":
            halved += 1

        played = won + lost + halved
        remaining = total - played

        # Running status for this hole
        if lead > 0:
            hole_status[h.hole_number] = f"{lead} UP"
        elif lead < 0:
            hole_status[h.hole_number] = f"{abs(lead)} DN"
        else:
            hole_status[h.hole_number] = "AS"

        # Check if match is closed (only early — not at final hole)
        if closed_at is None and remaining > 0 and abs(lead) > remaining:
            closed_at = h.hole_number
            break

    played = won + lost + halved

    if played == 0:
        return MatchResult(
            holes_won=0, holes_lost=0, holes_halved=0,
            holes_played=0, total_holes=total,
            result_text="—", is_complete=False,
            closed_at=None, hole_status={},
        )

    remaining = total - played
    is_complete = played == total or closed_at is not None

    if closed_at is not None:
        # Match closed early — standard "X&Y" format
        margin = abs(lead)
        if lead > 0:
            text = f"W {margin}&{remaining}"
        else:
            text = f"L {margin}&{remaining}"
    elif played == total:
        # All holes played
        if lead > 0:
            text = f"W {lead} UP"
        elif lead < 0:
            text = f"L {abs(lead)} DN"
        else:
            text = "AS"
    else:
        # In progress
        if lead > 0:
            text = f"{lead} UP thru {played}"
        elif lead < 0:
            text = f"{abs(lead)} DN thru {played}"
        else:
            text = f"AS thru {played}"

    return MatchResult(
        holes_won=won,
        holes_lost=lost,
        holes_halved=halved,
        holes_played=played,
        total_holes=total,
        result_text=text,
        is_complete=is_complete,
        closed_at=closed_at,
        hole_status=hole_status,
    )
