"""Open-Meteo Marine API: free hourly wave/wind forecast and historical data.

No API key required. Provides:
- Historical marine data (several years back)
- 7-day hourly forecast

Docs: https://open-meteo.com/en/docs/marine-weather-api
"""

import logging
import requests
from datetime import date, datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

MARINE_API_URL = "https://marine-api.open-meteo.com/v1/marine"
WEATHER_API_URL = "https://api.open-meteo.com/v1/forecast"

MARINE_HOURLY_VARS = [
    "wave_height",
    "wave_direction",
    "wave_period",
    "wind_wave_height",
    "wind_wave_direction",
    "wind_wave_period",
    "swell_wave_height",
    "swell_wave_direction",
    "swell_wave_period",
    "swell_wave_peak_period",
]

WEATHER_HOURLY_VARS = [
    "wind_speed_10m",
    "wind_direction_10m",
]


def fetch_marine(
    lat: float,
    lon: float,
    start_date: date,
    end_date: date,
    is_forecast: bool = False,
) -> list[dict]:
    """Fetch hourly marine data for a given location and date range.

    Args:
        lat: Latitude
        lon: Longitude
        start_date: First day (inclusive)
        end_date: Last day (inclusive)
        is_forecast: Whether this is forecast data (True) or historical (False)

    Returns:
        List of dicts with hourly conditions
    """
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": ",".join(MARINE_HOURLY_VARS),
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "timezone": "Asia/Tokyo",
    }

    resp = requests.get(MARINE_API_URL, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    # Fetch wind separately from weather API (more reliable)
    wind_params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": ",".join(WEATHER_HOURLY_VARS),
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "timezone": "Asia/Tokyo",
        "wind_speed_unit": "ms",
    }
    wind_resp = requests.get(WEATHER_API_URL, params=wind_params, timeout=30)
    wind_resp.raise_for_status()
    wind_data = wind_resp.json()

    hourly = data["hourly"]
    wind_hourly = wind_data["hourly"]
    n = len(hourly["time"])

    records = []
    for i in range(n):
        records.append({
            "timestamp": hourly["time"][i],
            "wave_height_m": _get(hourly, "wave_height", i),
            "wave_period_s": _get(hourly, "wave_period", i),
            "wave_direction_deg": _get(hourly, "wave_direction", i),
            "swell_height_m": _get(hourly, "swell_wave_height", i),
            "swell_period_s": _get(hourly, "swell_wave_period", i),
            "swell_direction_deg": _get(hourly, "swell_wave_direction", i),
            "wind_speed_ms": _get(wind_hourly, "wind_speed_10m", i),
            "wind_direction_deg": _get(wind_hourly, "wind_direction_10m", i),
            "data_source": "open_meteo",
            "is_forecast": 1 if is_forecast else 0,
        })

    return records


def fetch_forecast(lat: float, lon: float, days: int = 7) -> list[dict]:
    """Fetch 7-day hourly forecast for a spot."""
    today = date.today()
    return fetch_marine(lat, lon, today, today + timedelta(days=days), is_forecast=True)


def fetch_historical(lat: float, lon: float, start_date: date, end_date: date) -> list[dict]:
    """Fetch historical marine data (backfill)."""
    return fetch_marine(lat, lon, start_date, end_date, is_forecast=False)


def _get(d: dict, key: str, i: int) -> Optional[float]:
    if key not in d:
        return None
    v = d[key][i]
    return float(v) if v is not None else None


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    # Test: fetch forecast for Ichinomiya
    records = fetch_forecast(35.365, 140.367, days=3)
    print(f"Got {len(records)} hourly records")
    for r in records[:3]:
        print(r)
