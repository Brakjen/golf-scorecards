"""Tests for the weather service."""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, patch

import pytest

from golf_scorecards.weather.models import WeatherData, WMO_ICONS
from golf_scorecards.weather.service import _parse_response, _round_hours, fetch_weather


class TestWeatherData:
    def test_icon_clear(self) -> None:
        w = WeatherData(weather_code=0, temperature=20.0, wind_speed=3.0, precipitation=0.0)
        assert w.icon == "☀️"
        assert w.label == "Clear"

    def test_icon_rain(self) -> None:
        w = WeatherData(weather_code=63, temperature=10.0, wind_speed=5.0, precipitation=3.2)
        assert w.icon == "🌧️"
        assert w.label == "Rain"

    def test_icon_unknown_code(self) -> None:
        w = WeatherData(weather_code=999, temperature=15.0, wind_speed=2.0, precipitation=0.0)
        assert w.icon == "❓"
        assert w.label == "Unknown"

    def test_windy_threshold(self) -> None:
        calm = WeatherData(weather_code=0, temperature=20.0, wind_speed=9.9, precipitation=0.0)
        assert not calm.windy
        windy = WeatherData(weather_code=0, temperature=20.0, wind_speed=10.0, precipitation=0.0)
        assert windy.windy

    def test_frozen(self) -> None:
        w = WeatherData(weather_code=0, temperature=20.0, wind_speed=3.0, precipitation=0.0)
        with pytest.raises(AttributeError):
            w.weather_code = 1  # type: ignore[misc]


class TestRoundHours:
    def test_no_tee_time_returns_default(self) -> None:
        assert _round_hours(None) == list(range(8, 17))
        assert _round_hours("") == list(range(8, 17))

    def test_18_holes(self) -> None:
        assert _round_hours("10:00", "18") == list(range(10, 15))

    def test_9_holes_front(self) -> None:
        assert _round_hours("08:30", "front_9") == list(range(8, 10))

    def test_9_holes_back(self) -> None:
        assert _round_hours("14:00", "back_9") == list(range(14, 16))

    def test_late_tee_time_clamped_to_24(self) -> None:
        hours = _round_hours("21:00", "18")
        assert hours == list(range(21, 24))

    def test_invalid_tee_time_returns_default(self) -> None:
        assert _round_hours("bad") == list(range(8, 17))


class TestParseResponse:
    def test_typical_response(self) -> None:
        data = {
            "hourly": {
                "time": [f"2026-05-10T{h:02d}:00" for h in range(24)],
                "weather_code": [0] * 8 + [2, 2, 3, 3, 61, 2, 2, 2, 0] + [0] * 7,
                "temperature_2m": [5.0] * 8 + [10.0, 12.0, 14.0, 15.0, 13.0, 12.0, 11.0, 10.0, 9.0] + [6.0] * 7,
                "wind_speed_10m": [2.0] * 8 + [5.0, 6.0, 7.0, 8.0, 9.0, 7.0, 6.0, 5.0, 4.0] + [2.0] * 7,
                "precipitation": [0.0] * 8 + [0.0, 0.0, 0.0, 0.0, 1.5, 0.0, 0.0, 0.0, 0.0] + [0.0] * 7,
            }
        }
        result = _parse_response(data)
        assert result is not None
        # Dominant code in 08-16 window should be 61 (the max)
        assert result.weather_code == 61
        assert result.precipitation == 1.5
        # Wind is max in window
        assert result.wind_speed == 9.0

    def test_empty_hourly(self) -> None:
        assert _parse_response({"hourly": {}}) is None
        assert _parse_response({}) is None

    def test_no_times(self) -> None:
        assert _parse_response({"hourly": {"time": []}}) is None

    def test_all_hours_fallback(self) -> None:
        """When no hours match 08-16, uses all hours."""
        data = {
            "hourly": {
                "time": ["2026-05-10T03:00", "2026-05-10T04:00"],
                "weather_code": [0, 2],
                "temperature_2m": [8.0, 9.0],
                "wind_speed_10m": [3.0, 4.0],
                "precipitation": [0.0, 0.5],
            }
        }
        result = _parse_response(data)
        assert result is not None
        assert result.weather_code == 2
        assert result.temperature == 8.5

    def test_custom_hours_window(self) -> None:
        """When explicit hours provided, only those hours count."""
        data = {
            "hourly": {
                "time": [f"2026-05-10T{h:02d}:00" for h in range(24)],
                "weather_code": [0] * 10 + [63, 63] + [0] * 12,
                "temperature_2m": [5.0] * 10 + [12.0, 13.0] + [5.0] * 12,
                "wind_speed_10m": [2.0] * 10 + [8.0, 9.0] + [2.0] * 12,
                "precipitation": [0.0] * 10 + [2.0, 3.0] + [0.0] * 12,
            }
        }
        result = _parse_response(data, hours=[10, 11])
        assert result is not None
        assert result.weather_code == 63
        assert result.temperature == 12.5
        assert result.wind_speed == 9.0
        assert result.precipitation == 5.0


class TestFetchWeather:
    @pytest.mark.asyncio
    async def test_returns_none_on_network_error(self) -> None:
        with patch("golf_scorecards.weather.service.httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)
            mock_instance.get = AsyncMock(side_effect=Exception("network down"))
            mock_client.return_value = mock_instance
            result = await fetch_weather(58.89, 5.68, date(2026, 5, 1))
            assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_for_far_future(self) -> None:
        result = await fetch_weather(58.89, 5.68, date(2099, 1, 1))
        assert result is None

    @pytest.mark.asyncio
    async def test_uses_archive_for_past_dates(self) -> None:
        with patch("golf_scorecards.weather.service.httpx.AsyncClient") as mock_client:
            response_data = {
                "hourly": {
                    "time": [f"2025-06-01T{h:02d}:00" for h in range(24)],
                    "weather_code": [0] * 24,
                    "temperature_2m": [18.0] * 24,
                    "wind_speed_10m": [3.0] * 24,
                    "precipitation": [0.0] * 24,
                }
            }
            mock_resp = AsyncMock()
            mock_resp.status_code = 200
            mock_resp.raise_for_status = lambda: None
            mock_resp.json.return_value = response_data
            # Make json() not async — httpx Response.json() is synchronous
            mock_resp.json = lambda: response_data

            mock_instance = AsyncMock()
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)
            mock_instance.get.return_value = mock_resp
            mock_client.return_value = mock_instance

            result = await fetch_weather(58.89, 5.68, date(2025, 6, 1))
            assert result is not None
            assert result.weather_code == 0
            assert result.temperature == 18.0

            # Check it used the archive URL
            call_args = mock_instance.get.call_args
            assert "archive" in call_args.args[0]


class TestWmoIcons:
    def test_all_documented_codes_have_entries(self) -> None:
        """Verify known WMO codes have icons."""
        known_codes = [0, 1, 2, 3, 45, 48, 51, 53, 55, 61, 63, 65, 71, 73, 75, 80, 81, 82, 95]
        for code in known_codes:
            assert code in WMO_ICONS, f"Missing WMO code {code}"
            icon, label = WMO_ICONS[code]
            assert len(icon) > 0
            assert len(label) > 0
