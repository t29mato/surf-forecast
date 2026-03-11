"""JMA tide data retrieval.

JMA provides predicted tidal levels via their web service.
This module fetches tidal data for major Japanese observation stations.

API: https://www.data.jma.go.jp/gmd/kaiyou/db/tide/suisan/index.php
"""

import logging
import re
import requests
from datetime import date, datetime
from typing import Optional

logger = logging.getLogger(__name__)

# JMA station codes for major surf regions
# Full list: https://www.data.jma.go.jp/gmd/kaiyou/db/tide/suisan/station.php
STATION_CODES = {
    "大洗": "85",       # Ibaraki
    "千葉": "97",       # Chiba
    "横浜": "99",       # Kanagawa
    "下田": "105",      # Shizuoka/Izu
    "御前崎": "110",    # Shizuoka
    "三宅島": "116",    # Izu Islands
    "高知": "143",      # Kochi
    "宿毛": "147",      # Kochi west
    "宮崎": "159",      # Miyazaki
    "大分": "155",      # Oita
    "鹿児島": "168",    # Kagoshima
    "那覇": "181",      # Okinawa
    "新潟": "62",       # Niigata
    "輪島": "74",       # Ishikawa
    "境": "82",         # Tottori
    "田辺": "130",      # Wakayama
    "小樽": "11",       # Hokkaido
}

JMA_TIDE_URL = "https://www.data.jma.go.jp/gmd/kaiyou/db/tide/suisan/txt/{year}/{station}{year}{month:02d}.txt"


def fetch_tide_month(station_name: str, year: int, month: int) -> list[dict]:
    """Fetch hourly tidal data for a JMA station and month.

    Args:
        station_name: Japanese station name (key in STATION_CODES)
        year: e.g. 2024
        month: 1-12

    Returns:
        List of dicts: {"timestamp": "YYYY-MM-DDTHH:00", "tide_height_cm": float}
    """
    station_code = STATION_CODES.get(station_name)
    if not station_code:
        logger.warning(f"Unknown JMA station: {station_name}")
        return []

    url = JMA_TIDE_URL.format(
        year=year,
        station=station_code,
        month=month,
    )

    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        return _parse_jma_tide_txt(resp.text, year, month)
    except requests.HTTPError as e:
        logger.warning(f"JMA tide fetch failed for {station_name} {year}-{month:02d}: {e}")
        return []


def _parse_jma_tide_txt(text: str, year: int, month: int) -> list[dict]:
    """Parse JMA tide text format.

    Format: Each line represents one day.
    Columns: day, 00h, 01h, ..., 23h tide heights in cm.
    """
    records = []
    for line in text.strip().split("\n"):
        parts = line.split()
        if len(parts) < 25:
            continue
        try:
            day = int(parts[0])
        except ValueError:
            continue

        for hour in range(24):
            try:
                height = float(parts[hour + 1])
            except (ValueError, IndexError):
                height = None

            ts = datetime(year, month, day, hour)
            records.append({
                "timestamp": ts.isoformat(),
                "tide_height_cm": height,
            })

    return records


def fetch_tide_forecast_open_meteo(lat: float, lon: float) -> list[dict]:
    """Fetch tidal height from Open-Meteo ocean API (7-day forecast).

    Open-Meteo provides ocean current and some tidal data.
    Used as fallback when JMA data is unavailable.
    """
    import requests
    url = "https://marine-api.open-meteo.com/v1/marine"
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": "ocean_current_velocity",
        "timezone": "Asia/Tokyo",
        "forecast_days": 7,
    }
    # Note: Open-Meteo doesn't provide tidal heights directly.
    # Tide computation from astronomical data is preferred.
    # This is a placeholder for future integration.
    return []


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    records = fetch_tide_month("千葉", 2024, 1)
    print(f"Got {len(records)} tide records")
    for r in records[:5]:
        print(r)
