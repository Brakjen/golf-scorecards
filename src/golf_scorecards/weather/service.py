"""Fetch weather data from Open-Meteo API.

Uses the historical archive API for past dates and the forecast API
for today/future dates.  No API key required.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

import httpx

from golf_scorecards.weather.models import WeatherData

logger = logging.getLogger(__name__)

_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
_ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"

# Default round window when no tee time given.
_DEFAULT_HOURS = list(range(8, 17))  # 08:00 – 16:00


def _round_hours(tee_time: str | None, holes_played: str = "18") -> list[int]:
    """Compute the hours to include based on tee time and hole count.

    9 holes ≈ 2 hours, 18 holes ≈ 4.5 hours (rounded up to 5).
    """
    if not tee_time:
        return _DEFAULT_HOURS
    try:
        start_hour = int(tee_time.split(":")[0])
    except (ValueError, IndexError):
        return _DEFAULT_HOURS
    duration = 2 if holes_played in ("front_9", "back_9") else 5
    return list(range(start_hour, min(start_hour + duration, 24)))


async def fetch_weather(
    latitude: float,
    longitude: float,
    round_date: date,
    *,
    tee_time: str | None = None,
    holes_played: str = "18",
) -> WeatherData | None:
    """Fetch weather for a location and date.

    Returns ``None`` if the API call fails (network error, rate limit,
    unavailable date range, etc.) so callers can proceed without weather.
    """
    today = date.today()

    # Open-Meteo forecast covers today + ~16 days ahead.
    # Archive covers 1940 to yesterday.
    if round_date > today + timedelta(days=16):
        return None  # too far in the future

    if round_date < today:
        url = _ARCHIVE_URL
    else:
        url = _FORECAST_URL

    params = {
        "latitude": latitude,
        "longitude": longitude,
        "start_date": round_date.isoformat(),
        "end_date": round_date.isoformat(),
        "hourly": "weather_code,temperature_2m,wind_speed_10m,precipitation",
        "wind_speed_unit": "ms",
        "timezone": "auto",
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
    except Exception:
        logger.warning("Weather fetch failed for %s at (%s, %s)", round_date, latitude, longitude, exc_info=True)
        return None

    return _parse_response(data, _round_hours(tee_time, holes_played))


def _parse_response(data: dict, hours: list[int] | None = None) -> WeatherData | None:
    """Extract round-window averages from hourly data."""
    if hours is None:
        hours = _DEFAULT_HOURS
    hourly = data.get("hourly")
    if not hourly:
        return None

    times = hourly.get("time", [])
    codes = hourly.get("weather_code", [])
    temps = hourly.get("temperature_2m", [])
    winds = hourly.get("wind_speed_10m", [])
    precip = hourly.get("precipitation", [])

    if not times:
        return None

    # Extract hour from ISO timestamps ("2026-05-10T08:00" → 8)
    indices = []
    for i, t in enumerate(times):
        try:
            hour = int(t.split("T")[1].split(":")[0])
        except (IndexError, ValueError):
            continue
        if hour in hours:
            indices.append(i)

    if not indices:
        # Fallback: use all hours
        indices = list(range(len(times)))

    # Dominant weather code (most severe / highest code value)
    window_codes = [codes[i] for i in indices if i < len(codes) and codes[i] is not None]
    window_temps = [temps[i] for i in indices if i < len(temps) and temps[i] is not None]
    window_winds = [winds[i] for i in indices if i < len(winds) and winds[i] is not None]
    window_precip = [precip[i] for i in indices if i < len(precip) and precip[i] is not None]

    if not window_codes or not window_temps:
        return None

    return WeatherData(
        weather_code=max(window_codes),
        temperature=round(sum(window_temps) / len(window_temps), 1),
        wind_speed=round(max(window_winds), 1) if window_winds else 0.0,
        precipitation=round(sum(window_precip), 1) if window_precip else 0.0,
    )
