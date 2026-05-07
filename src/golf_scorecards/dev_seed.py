"""Generate realistic dummy data for DEV mode.

Populates an empty database with 30 rounds and 15 practice sessions showing
a player improving from ~22 handicap to ~14 handicap. Short game improvement
is the driver — putting and pitching averages decrease over time.
"""

from __future__ import annotations

import json
import random
import sqlite3
import uuid
from datetime import date, timedelta
from pathlib import Path


# ── Course data (Forus tee 63) ──────────────────────────────────────────

FORUS_HOLES = [
    {"hole_number": 1, "par": 4, "distance": 330, "handicap": 6},
    {"hole_number": 2, "par": 4, "distance": 359, "handicap": 8},
    {"hole_number": 3, "par": 4, "distance": 348, "handicap": 4},
    {"hole_number": 4, "par": 3, "distance": 139, "handicap": 16},
    {"hole_number": 5, "par": 5, "distance": 491, "handicap": 14},
    {"hole_number": 6, "par": 4, "distance": 367, "handicap": 2},
    {"hole_number": 7, "par": 3, "distance": 153, "handicap": 18},
    {"hole_number": 8, "par": 4, "distance": 377, "handicap": 10},
    {"hole_number": 9, "par": 5, "distance": 490, "handicap": 12},
    {"hole_number": 10, "par": 4, "distance": 348, "handicap": 11},
    {"hole_number": 11, "par": 3, "distance": 193, "handicap": 15},
    {"hole_number": 12, "par": 5, "distance": 501, "handicap": 9},
    {"hole_number": 13, "par": 4, "distance": 370, "handicap": 3},
    {"hole_number": 14, "par": 4, "distance": 250, "handicap": 17},
    {"hole_number": 15, "par": 4, "distance": 387, "handicap": 7},
    {"hole_number": 16, "par": 4, "distance": 394, "handicap": 1},
    {"hole_number": 17, "par": 3, "distance": 188, "handicap": 13},
    {"hole_number": 18, "par": 5, "distance": 525, "handicap": 5},
]

COURSE_SNAPSHOT = json.dumps({
    "club_name": "Sola golfklubb",
    "course_name": "Forus",
    "course_slug": "sola-golfklubb-forus",
    "tee_name": "63",
    "par_total": 72,
    "total_distance": 6210,
    "holes": FORUS_HOLES,
})

COURSE_RATING = 72.9
SLOPE_RATING = 144

# Practice station slugs in order
STATION_SLUGS = [
    "putt-short", "putt-medium", "putt-lag",
    "pitch-40", "pitch-60", "pitch-80", "bunker",
]


def _generate_hole_score(par: int, hcp_rank: int, player_hcp: float) -> dict:
    """Simulate a hole shot-by-shot to produce realistic, correlated stats.

    Models: tee shot → approach(es) → short game → putting, with each phase
    producing outcomes that feed into the next. Skill improves as player_hcp
    drops (22 → 14), with short game being the primary driver of improvement.

    Args:
        par: Par for this hole (3, 4, or 5).
        hcp_rank: Hole difficulty rank (1=hardest, 18=easiest).
        player_hcp: Current handicap (22.0 down to 14.0).

    Returns:
        Dict with score, putts, penalty_strokes, miss_direction, up_and_down,
        sand_save, sz_in_reg, down_in_3, nfs, notes.
    """
    # ── Skill parameters (improve linearly from hcp 22 → 14) ──────────
    # progress: 0.0 at hcp 22, 1.0 at hcp 14
    progress = (22.0 - player_hcp) / 8.0

    # Probability of hitting fairway (tee shot quality)
    fairway_pct = 0.35 + 0.15 * progress  # 35% → 50%
    # Probability of GIR given fairway vs rough
    gir_from_fairway = 0.22 + 0.18 * progress  # 22% → 40%
    gir_from_rough = 0.08 + 0.10 * progress    # 8% → 18%
    # Short game: probability of getting close (within 1-putt range)
    chip_close_pct = 0.15 + 0.15 * progress    # 15% → 30%
    # Putting: probability of 1-putt from GIR distance
    one_putt_gir_pct = 0.10 + 0.06 * progress  # 10% → 16%
    # Probability of 3-putt (lag putting weakness)
    three_putt_pct = 0.18 - 0.10 * progress    # 18% → 8%
    # Penalty chance (OB, water, lost ball)
    penalty_pct = 0.07 - 0.03 * progress       # 7% → 4%
    # Duff/chunk: approach completely fails, need another full shot
    duff_approach_pct = 0.10 - 0.06 * progress  # 10% → 4%

    # Harder holes increase miss/penalty chance slightly
    difficulty_mod = (10 - hcp_rank) * 0.008  # -0.06 to +0.07

    # ── Tee shot ──────────────────────────────────────────────────────
    penalty_strokes = 0
    miss_direction = None

    if random.random() < penalty_pct + difficulty_mod * 0.5:
        # Penalty off the tee: OB or water
        penalty_strokes = 1
        miss_direction = random.choice(["left", "right"])
        in_fairway = False
        # Re-tee or drop: costs a stroke, treat as being in rough
    elif random.random() < fairway_pct - difficulty_mod:
        in_fairway = True
    else:
        in_fairway = False
        miss_direction = random.choice(["left", "right", None])

    # ── Approach (par 4/5) or tee shot to green (par 3) ───────────────
    extra_approach_strokes = 0  # duffs, chunks, topped shots

    if par == 3:
        # Par 3: tee shot IS the approach
        gir_chance = gir_from_fairway * 0.85  # slightly harder (long iron/hybrid)
        if penalty_strokes > 0:
            hit_green = False
        elif random.random() < duff_approach_pct:
            hit_green = False
            extra_approach_strokes = 1  # topped/chunked, short of green
        else:
            hit_green = random.random() < gir_chance
    elif par == 4:
        gir_chance = gir_from_fairway if in_fairway else gir_from_rough
        gir_chance -= difficulty_mod * 0.5
        if penalty_strokes > 0:
            # After penalty, approach is from an awkward spot
            hit_green = random.random() < gir_from_rough * 0.5
        elif random.random() < duff_approach_pct:
            hit_green = False
            extra_approach_strokes = 1  # duffed approach
        else:
            hit_green = random.random() < gir_chance
    else:
        # Par 5: need to reach in 3 (or rare 2 for eagle try)
        reach_in_2 = random.random() < 0.02 + 0.03 * progress
        if reach_in_2 and penalty_strokes == 0:
            hit_green = True
        elif penalty_strokes > 0:
            # After penalty on par 5: scrambling
            hit_green = random.random() < 0.15
            if not hit_green and random.random() < duff_approach_pct:
                extra_approach_strokes = 1
        else:
            # Third shot is a wedge/short iron
            third_shot_chance = 0.35 + 0.20 * progress  # 35% → 55%
            if random.random() < duff_approach_pct * 0.7:
                hit_green = False
                extra_approach_strokes = 1
            else:
                hit_green = random.random() < third_shot_chance

    # ── Short game (if green missed) ──────────────────────────────────
    chip_strokes = 0
    in_bunker = False
    got_close = False  # within 1-putt range after chip

    if not hit_green:
        # Did the miss end up in a bunker?
        in_bunker = random.random() < 0.18

        if in_bunker:
            # Bunker shots: harder to get close
            bunker_close_pct = chip_close_pct * 0.5
            got_close = random.random() < bunker_close_pct
        else:
            got_close = random.random() < chip_close_pct

        chip_strokes = 1

        # Bad chip: duff/skull requiring a second chip
        bad_chip_pct = 0.12 - 0.06 * progress  # 12% → 6%
        if random.random() < bad_chip_pct:
            chip_strokes = 2
            got_close = random.random() < 0.55  # second attempt usually ok

    # ── Putting ───────────────────────────────────────────────────────
    if hit_green:
        # GIR: typical 2-putt, chance of 1 or 3
        if random.random() < one_putt_gir_pct:
            putts = 1
        elif random.random() < three_putt_pct:
            putts = 3
        else:
            putts = 2
    elif got_close:
        # Chipped close: high chance of 1-putt
        if random.random() < 0.75 + 0.10 * progress:
            putts = 1
        else:
            putts = 2
    else:
        # Chip wasn't close: mostly 2-putt, some 3-putt
        if random.random() < 0.08:
            putts = 1  # lucky long putt
        elif random.random() < three_putt_pct * 1.5:
            putts = 3
        else:
            putts = 2

    # ── Compute total score ───────────────────────────────────────────
    if par == 3:
        tee_to_green = 1 + extra_approach_strokes if hit_green else (1 + extra_approach_strokes + chip_strokes)
    elif par == 4:
        tee_to_green = 2 + extra_approach_strokes if hit_green else (2 + extra_approach_strokes + chip_strokes)
    else:  # par 5
        tee_to_green = 3 + extra_approach_strokes if hit_green else (3 + extra_approach_strokes + chip_strokes)

    score = tee_to_green + putts + penalty_strokes

    # ── Derived stats ─────────────────────────────────────────────────
    gir = hit_green  # already boolean

    # Up-and-down: missed green but holed out in (chip_strokes + putts) <= 2
    up_and_down = None
    if not gir:
        up_and_down = 1 if (chip_strokes + putts <= 2) else 0

    # Sand save: up-and-down from a bunker
    sand_save = None
    if in_bunker:
        sand_save = 1 if (chip_strokes + putts <= 2) else 0

    # Scoring zone in regulation: approach was from scoring zone distance
    sz_in_reg = None
    if par >= 4 and not gir:
        sz_in_reg = 1 if random.random() < 0.55 else 0

    # Down in 3: completed the hole from around/near the green in 3 or fewer
    down_in_3 = None
    if not gir and (par == 5 or par == 4):
        down_in_3 = 1 if (chip_strokes + putts <= 3) else 0

    return {
        "score": score,
        "putts": putts,
        "penalty_strokes": penalty_strokes,
        "miss_direction": miss_direction,
        "up_and_down": up_and_down,
        "sand_save": sand_save,
        "sz_in_reg": sz_in_reg,
        "down_in_3": down_in_3,
        "nfs": 0,
        "notes": None,
    }


def _generate_practice_strokes(station_slug: str, session_idx: int) -> list[int]:
    """Generate 7 stroke values for a station.

    Improvement curve: earlier sessions have higher averages.
    Putting stations: 1-3 strokes. Pitch/bunker: 2-5 strokes.
    """
    # Progress: 0.0 (first session) → 1.0 (last session)
    progress = session_idx / 14.0

    if station_slug == "putt-short":
        # 1-2m: mostly 1s, some 2s. Improves from ~1.4 avg to ~1.15
        weights = [0.55 + 0.25 * progress, 0.35 - 0.15 * progress, 0.10 - 0.08 * progress]
        choices = [1, 2, 3]
    elif station_slug == "putt-medium":
        # 5-8m: mix of 2s and 3s. Improves from ~2.4 to ~2.0
        weights = [0.10 + 0.15 * progress, 0.45 + 0.15 * progress, 0.35 - 0.20 * progress, 0.10 - 0.08 * progress]
        choices = [1, 2, 3, 4]
    elif station_slug == "putt-lag":
        # 10-15m: lots of 2s and 3s. Improves from ~2.8 to ~2.3
        weights = [0.05 + 0.10 * progress, 0.30 + 0.15 * progress, 0.40 - 0.10 * progress, 0.20 - 0.12 * progress, 0.05 - 0.03 * progress]
        choices = [1, 2, 3, 4, 5]
    elif station_slug == "pitch-40":
        # 40m pitch: improves from ~3.0 to ~2.5
        weights = [0.05 + 0.10 * progress, 0.25 + 0.15 * progress, 0.40 - 0.10 * progress, 0.25 - 0.12 * progress, 0.05 - 0.03 * progress]
        choices = [1, 2, 3, 4, 5]
    elif station_slug == "pitch-60":
        # 60m pitch: improves from ~3.2 to ~2.7
        weights = [0.03 + 0.07 * progress, 0.20 + 0.13 * progress, 0.42 - 0.08 * progress, 0.28 - 0.10 * progress, 0.07 - 0.02 * progress]
        choices = [1, 2, 3, 4, 5]
    elif station_slug == "pitch-80":
        # 80m pitch: improves from ~3.4 to ~2.9
        weights = [0.02 + 0.05 * progress, 0.15 + 0.12 * progress, 0.40 - 0.05 * progress, 0.33 - 0.10 * progress, 0.10 - 0.02 * progress]
        choices = [1, 2, 3, 4, 5]
    else:  # bunker
        # Bunker: improves from ~3.3 to ~2.6
        weights = [0.03 + 0.08 * progress, 0.18 + 0.15 * progress, 0.40 - 0.05 * progress, 0.30 - 0.13 * progress, 0.09 - 0.05 * progress]
        choices = [1, 2, 3, 4, 5]

    # Normalize weights
    total = sum(weights)
    weights = [w / total for w in weights]

    return random.choices(choices, weights=weights, k=7)


def seed_database(db_path: str) -> None:
    """Populate the database with 30 rounds and 15 practice sessions.

    The data tells a story of improvement from HC 22 to HC 14 over ~8 months,
    driven by short game gains (fewer 3-putts, better up-and-downs, lower
    practice station averages).

    Args:
        db_path: Path to the SQLite database to populate.
    """
    random.seed(42)  # Reproducible data

    conn = sqlite3.connect(db_path)
    try:
        _seed_rounds(conn)
        _seed_practice_sessions(conn)
        conn.commit()
    finally:
        conn.close()


def _seed_rounds(conn: sqlite3.Connection) -> None:
    """Insert 30 rounds showing HC 22 → 14 progression."""
    start_date = date(2025, 10, 1)

    for i in range(30):
        round_id = uuid.uuid4().hex
        # Handicap drops linearly: 22.0 → 14.0
        player_hcp = 22.0 - (8.0 * i / 29.0)

        # "Form" for this round: a small swing that adds slight variation
        # but preserves the overall downward trend. Good days and bad days
        # happen but bad days become rarer as skill improves.
        # Noise is biased slightly high (bad) for high HC, slightly low for low HC
        form_noise = random.gauss(0.5 - 0.5 * (i / 29.0), 0.6)
        effective_hcp = max(12.0, min(24.0, player_hcp + form_noise))

        # Playing handicap (rounded)
        playing_hcp = round(player_hcp)
        # Round date: spread over ~8 months (every ~8 days)
        round_date = start_date + timedelta(days=i * 8 + random.randint(-2, 2))
        now = f"{round_date}T10:00:00"

        conn.execute(
            """INSERT INTO rounds
               (id, course_slug, tee_name, player_name, round_date,
                handicap_index, handicap_profile, playing_handicap,
                course_rating, slope_rating, scoring_mode, target_score,
                holes_played, course_snapshot, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                round_id, "sola-golfklubb-forus", "63", "Dev Player",
                round_date.isoformat(), player_hcp, "men", playing_hcp,
                COURSE_RATING, SLOPE_RATING, "stroke", None,
                "18", COURSE_SNAPSHOT, now, now,
            ),
        )

        # Generate hole scores using effective_hcp (with form applied)
        for hole in FORUS_HOLES:
            hole_data = _generate_hole_score(hole["par"], hole["handicap"], effective_hcp)
            conn.execute(
                """INSERT INTO round_holes
                   (id, round_id, hole_number, par, distance, handicap,
                    score, putts, penalty_strokes, miss_direction,
                    up_and_down, sand_save, sz_in_reg, down_in_3, nfs, notes)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    uuid.uuid4().hex, round_id, hole["hole_number"],
                    hole["par"], hole["distance"], hole["handicap"],
                    hole_data["score"], hole_data["putts"],
                    hole_data["penalty_strokes"], hole_data["miss_direction"],
                    hole_data["up_and_down"], hole_data["sand_save"],
                    hole_data["sz_in_reg"], hole_data["down_in_3"],
                    hole_data["nfs"], hole_data["notes"],
                ),
            )


def _seed_practice_sessions(conn: sqlite3.Connection) -> None:
    """Insert 15 practice sessions showing short game improvement."""
    start_date = date(2025, 10, 5)
    locations = [
        "Solastranden practice area",
        "Forus putting green",
        "Solastranden chipping",
        "Forus short game area",
        None,  # some sessions without a title
    ]
    notes_pool = [
        "Calm, soft greens",
        "Windy, firm greens",
        "Morning dew, slow greens",
        "Good conditions",
        "Post-rain, heavy rough",
        None,
    ]

    for i in range(15):
        session_id = uuid.uuid4().hex
        session_date = start_date + timedelta(days=i * 16 + random.randint(-3, 3))
        now = f"{session_date}T14:00:00"
        title = random.choice(locations)
        notes = random.choice(notes_pool)

        conn.execute(
            """INSERT INTO practice_sessions (id, title, session_date, notes, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (session_id, title, session_date.isoformat(), notes, now),
        )

        # Some sessions are incomplete (skip some stations)
        if i < 3:
            # Early sessions: only putting stations done
            active_stations = STATION_SLUGS[:3]
        elif random.random() < 0.2:
            # Occasionally skip a station or two
            active_stations = random.sample(STATION_SLUGS, k=random.randint(4, 6))
        else:
            active_stations = STATION_SLUGS

        for station_slug in active_stations:
            strokes_list = _generate_practice_strokes(station_slug, i)
            for ball_num, strokes in enumerate(strokes_list, start=1):
                conn.execute(
                    """INSERT INTO practice_attempts
                       (id, session_id, station_slug, attempt_number, strokes, nfs)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (uuid.uuid4().hex, session_id, station_slug, ball_num, strokes, 0),
                )
