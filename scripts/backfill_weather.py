"""One-shot script to backfill weather data for existing rounds.

Usage (production via fly ssh):
    fly ssh console -a golf-scorecards-brakjen -C \
        "python /app/src/scripts/backfill_weather.py"

Usage (local dev):
    APP_ENV=development uv run python scripts/backfill_weather.py
"""

from __future__ import annotations

import asyncio
import sqlite3
import sys
from datetime import date

# Ensure the package is importable when run as a script
sys.path.insert(0, "src")

from golf_scorecards.catalog.repository import CourseCatalogRepository
from golf_scorecards.catalog.service import CatalogService
from golf_scorecards.config import get_settings
from golf_scorecards.weather.service import fetch_weather


async def backfill() -> None:
    settings = get_settings()
    db_path = settings.db_path

    # Build a slug → (lat, lng) lookup from the course catalog
    catalog = CatalogService(CourseCatalogRepository())
    coords: dict[str, tuple[float, float]] = {}
    for course in catalog.list_courses():
        if course.latitude is not None and course.longitude is not None:
            coords[course.course_slug] = (course.latitude, course.longitude)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    rows = conn.execute(
        """SELECT id, course_slug, round_date, tee_time, holes_played
           FROM rounds
           WHERE weather_code IS NULL
           ORDER BY round_date"""
    ).fetchall()

    print(f"Found {len(rows)} rounds without weather data.")
    if not rows:
        conn.close()
        return

    updated = 0
    skipped = 0
    for row in rows:
        slug = row["course_slug"]
        if slug not in coords:
            print(f"  SKIP {row['round_date']} — no coordinates for {slug}")
            skipped += 1
            continue

        lat, lng = coords[slug]
        rd = date.fromisoformat(row["round_date"])
        tee_time = row["tee_time"]
        holes = row["holes_played"] or "18"

        weather = await fetch_weather(
            lat, lng, rd, tee_time=tee_time, holes_played=holes,
        )
        if weather is None:
            print(f"  SKIP {row['round_date']} — API returned no data")
            skipped += 1
            continue

        conn.execute(
            """UPDATE rounds
               SET weather_code = ?, temperature = ?,
                   wind_speed = ?, precipitation = ?
               WHERE id = ?""",
            (
                weather.weather_code,
                weather.temperature,
                weather.wind_speed,
                weather.precipitation,
                row["id"],
            ),
        )
        updated += 1
        print(
            f"  OK   {row['round_date']} {slug:<30s} "
            f"{weather.weather_code:>3d}  {weather.temperature:5.1f}°C  "
            f"{weather.wind_speed:4.1f} m/s  {weather.precipitation:4.1f} mm"
        )

    conn.commit()
    conn.close()
    print(f"\nDone. Updated: {updated}, Skipped: {skipped}")


if __name__ == "__main__":
    asyncio.run(backfill())
