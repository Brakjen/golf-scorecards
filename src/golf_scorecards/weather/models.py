"""Weather data models."""

from __future__ import annotations

from dataclasses import dataclass

# WMO Weather Interpretation Codes → emoji + short label
# See: https://open-meteo.com/en/docs
WMO_ICONS: dict[int, tuple[str, str]] = {
    0: ("☀️", "Clear"),
    1: ("🌤️", "Mostly clear"),
    2: ("⛅", "Partly cloudy"),
    3: ("☁️", "Overcast"),
    45: ("🌫️", "Fog"),
    48: ("🌫️", "Rime fog"),
    51: ("🌦️", "Light drizzle"),
    53: ("🌦️", "Drizzle"),
    55: ("🌧️", "Dense drizzle"),
    56: ("🌧️", "Freezing drizzle"),
    57: ("🌧️", "Heavy freezing drizzle"),
    61: ("🌦️", "Light rain"),
    63: ("🌧️", "Rain"),
    65: ("🌧️", "Heavy rain"),
    66: ("🌧️", "Freezing rain"),
    67: ("🌧️", "Heavy freezing rain"),
    71: ("🌨️", "Light snow"),
    73: ("🌨️", "Snow"),
    75: ("🌨️", "Heavy snow"),
    77: ("🌨️", "Snow grains"),
    80: ("🌦️", "Light showers"),
    81: ("🌧️", "Showers"),
    82: ("🌧️", "Heavy showers"),
    85: ("🌨️", "Light snow showers"),
    86: ("🌨️", "Snow showers"),
    95: ("⛈️", "Thunderstorm"),
    96: ("⛈️", "Thunderstorm + hail"),
    99: ("⛈️", "Heavy thunderstorm + hail"),
}


@dataclass(frozen=True)
class WeatherData:
    """Weather snapshot for a round."""

    weather_code: int
    temperature: float  # °C
    wind_speed: float  # m/s (stored internally, displayed as needed)
    precipitation: float  # mm

    @property
    def icon(self) -> str:
        """Emoji icon for the weather code."""
        return WMO_ICONS.get(self.weather_code, ("❓", "Unknown"))[0]

    @property
    def label(self) -> str:
        """Short label for the weather code."""
        return WMO_ICONS.get(self.weather_code, ("❓", "Unknown"))[1]

    @property
    def windy(self) -> bool:
        """True when wind speed is ≥ 10 m/s (~36 km/h)."""
        return self.wind_speed >= 10.0
