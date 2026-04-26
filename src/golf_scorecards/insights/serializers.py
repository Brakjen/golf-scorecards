"""Serialize round data into structured text for the LLM prompt."""

from __future__ import annotations

from golf_scorecards.rounds.models import Round
from golf_scorecards.rounds.stats import QuickStats


def serialize_rounds(
    rounds: list[Round],
    stats: QuickStats,
    handicap_index: str | None = None,
) -> str:
    """Convert recent rounds and aggregate stats into a prompt-ready string.

    Args:
        rounds: Recent rounds with full hole data, newest first.
        stats: Pre-computed aggregate stats across the rounds.
        handicap_index: The player's current WHS handicap index.

    Returns:
        Formatted multi-line string suitable for the LLM user message.
    """
    lines: list[str] = []

    # ── Player profile ───────────────────────────────────
    if handicap_index is not None:
        lines.append(f"Player handicap index (HCI): {handicap_index}")

    # ── Aggregate stats ──────────────────────────────────
    lines.append(f"Rounds analysed: {stats.rounds_count}")
    if stats.avg_score is not None:
        lines.append(f"Avg gross score: {stats.avg_score}")
    if stats.avg_putts is not None:
        lines.append(f"Avg putts/round: {stats.avg_putts}")
    if stats.avg_penalties is not None:
        lines.append(f"Avg penalties/round: {stats.avg_penalties}")
    if stats.up_and_down_pct is not None:
        lines.append(f"Scrambling (up-and-down): {stats.up_and_down_pct}%")
    lines.append("")

    # ── Per-round summaries ──────────────────────────────
    for r in rounds:
        course_label = r.course_slug.replace("-", " ").title()
        header = f"Round: {r.round_date} | {course_label} (tee {r.tee_name})"
        if r.handicap_index is not None:
            header += f" | HCI {r.handicap_index}"
        if r.playing_handicap is not None:
            header += f" | PH {r.playing_handicap}"
        lines.append(header)

        scored = [h for h in r.holes if h.score is not None]
        if not scored:
            lines.append("  (no scores entered)")
            lines.append("")
            continue

        total_score = sum(h.score for h in scored if h.score is not None)
        total_par = sum(h.par for h in scored)
        total_putts = sum(h.putts for h in scored if h.putts is not None)
        rel = _relative(total_score - total_par)
        lines.append(f"  Score: {total_score} (par {total_par}, {rel})")
        lines.append(f"  Putts: {total_putts}")

        # Scoring zone stats
        sz_hits = sum(1 for h in scored if h.sz_in_reg == 1)
        sz_total = sum(1 for h in scored if h.sz_in_reg is not None)
        if sz_total:
            lines.append(f"  SZ in Reg: {sz_hits}/{sz_total}")

        d3_hits = sum(1 for h in scored if h.down_in_3 == 1)
        d3_total = sum(1 for h in scored if h.down_in_3 is not None)
        if d3_total:
            lines.append(f"  Down in 3: {d3_hits}/{d3_total}")

        ud_hits = sum(1 for h in scored if h.up_and_down == 1)
        ud_total = sum(1 for h in scored if h.up_and_down is not None)
        if ud_total:
            lines.append(f"  Up & Down: {ud_hits}/{ud_total}")

        nfs_total = sum(h.nfs for h in scored if h.nfs is not None and h.nfs > 0)
        if nfs_total:
            lines.append(f"  Non-functional strikes: {nfs_total}")

        pen_total = sum(
            h.penalty_strokes for h in scored if h.penalty_strokes is not None
        )
        if pen_total:
            lines.append(f"  Penalty strokes: {pen_total}")

        three_putts = sum(1 for h in scored if h.putts is not None and h.putts >= 3)
        if three_putts:
            lines.append(f"  3-putts: {three_putts}")

        # Miss direction summary
        misses: dict[str, int] = {}
        for h in scored:
            if h.miss_direction:
                misses[h.miss_direction] = misses.get(h.miss_direction, 0) + 1
        if misses:
            miss_parts = [f"{d} {c}" for d, c in sorted(misses.items(), key=lambda x: -x[1])]
            lines.append(f"  Green misses: {', '.join(miss_parts)}")

        # Hole-by-hole detail
        lines.append("  Holes:")
        for h in scored:
            parts = [f"H{h.hole_number}", f"P{h.par}"]
            if h.score is not None:
                diff = h.score - h.par
                parts.append(f"S{h.score}({_relative(diff)})")
            if h.putts is not None:
                parts.append(f"Pt{h.putts}")
            if h.nfs is not None and h.nfs > 0:
                parts.append(f"NFS{h.nfs}")
            if h.penalty_strokes is not None and h.penalty_strokes > 0:
                parts.append(f"Pen{h.penalty_strokes}")
            if h.miss_direction:
                parts.append(f"Miss:{h.miss_direction}")
            if h.up_and_down == 1:
                parts.append("U&D")
            if h.sand_save == 1:
                parts.append("Sand")
            lines.append(f"    {' | '.join(parts)}")

        lines.append("")

    return "\n".join(lines)


def _relative(diff: int) -> str:
    """Format a score-to-par difference as a relative string.

    Args:
        diff: Strokes over/under par (positive = over).

    Returns:
        e.g. ``"E"``, ``"+3"``, ``"-2"``.
    """
    if diff == 0:
        return "E"
    return f"+{diff}" if diff > 0 else str(diff)
