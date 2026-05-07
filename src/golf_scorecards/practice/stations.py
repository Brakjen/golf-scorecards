"""Station catalog — the fixed set of practice benchmark stations."""

from __future__ import annotations

from golf_scorecards.practice.models import Station

STATIONS: list[Station] = [
    Station(
        slug="putt-short",
        name="Putt 1-2m",
        category="putt",
        distance_m=2,
        description="7 different short putts, 1–2m, varying break and slope. Hole out each before moving to the next.",
    ),
    Station(
        slug="putt-medium",
        name="Putt 5–8m",
        category="putt",
        distance_m=6,
        description="7 different putts, 5–8m, varying break and slope. Hole out each before moving to the next.",
    ),
    Station(
        slug="putt-lag",
        name="Putt 10–15m",
        category="putt",
        distance_m=12,
        description="7 different lag putts, 10–15m, varying break. Hole out each before moving to the next.",
    ),
    Station(
        slug="pitch-40",
        name="Pitch 40m",
        category="pitch",
        distance_m=40,
        description="40m to pin, fairway lie. One ball at a time — pitch, hole out, walk back.",
    ),
    Station(
        slug="pitch-60",
        name="Pitch 60m",
        category="pitch",
        distance_m=60,
        description="60m to pin, fairway lie. One ball at a time — pitch, hole out, walk back.",
    ),
    Station(
        slug="pitch-80",
        name="Pitch 80m",
        category="pitch",
        distance_m=80,
        description="80m to pin, fairway lie. One ball at a time — pitch, hole out, walk back.",
    ),
    Station(
        slug="bunker",
        name="Bunker 8-10m",
        category="bunker",
        distance_m=9,
        description="Greenside bunker, 8–10m to pin. One ball at a time — splash out, hole out, walk back.",
    ),
]

STATION_MAP: dict[str, Station] = {s.slug: s for s in STATIONS}


def get_station(slug: str) -> Station:
    """Look up a station by its URL-safe slug.

    Args:
        slug: The station identifier (e.g. "putt-medium", "bunker").

    Returns:
        The matching ``Station`` object.

    Raises:
        KeyError: If no station exists with the given slug.
    """
    return STATION_MAP[slug]


def station_order() -> list[str]:
    """Return station slugs in the canonical execution order.

    The order matches the ``STATIONS`` list: putts first (short → lag),
    then pitches (40 → 80), then bunker.

    Returns:
        A list of slug strings, one per station.
    """
    return [s.slug for s in STATIONS]
