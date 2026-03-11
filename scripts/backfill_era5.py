"""ERA5 historical wave data backfill.

Downloads ERA5 monthly NetCDF files for Japan and imports hourly conditions
for each surf spot into the SQLite database.

Prerequisites:
    1. pip install cdsapi netCDF4
    2. Register at https://cds.climate.copernicus.eu/ and set up ~/.cdsapirc

Usage:
    python scripts/backfill_era5.py --start-year 1990 --end-year 2024
    python scripts/backfill_era5.py --start-year 2020 --end-year 2024  # quick test
"""

import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.db.models import get_conn, init_db
from src.ingestion.apis.era5 import fetch_era5_month, extract_spot_timeseries

logger = logging.getLogger(__name__)

SPOTS_JSON = Path(__file__).parent.parent / "data" / "spots.json"
ERA5_CACHE = Path(__file__).parent.parent / "data" / "era5_cache"


def backfill(start_year: int, end_year: int):
    init_db()
    spots = json.loads(SPOTS_JSON.read_text())

    # Register spots in DB
    with get_conn() as conn:
        for spot in spots:
            conn.execute(
                """
                INSERT OR IGNORE INTO spots
                    (id, name, prefecture, region, lat, lon,
                     orientation_deg, break_type, optimal_wave_height_m, nearest_tide_station)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    spot["id"], spot["name"], spot["prefecture"], spot["region"],
                    spot["lat"], spot["lon"], spot.get("orientation_deg"),
                    spot.get("break_type"), spot.get("optimal_wave_height_m"),
                    spot.get("nearest_tide_station"),
                ),
            )
        conn.commit()
    logger.info(f"Registered {len(spots)} spots in DB")

    total_inserted = 0
    for year in range(start_year, end_year + 1):
        for month in range(1, 13):
            logger.info(f"Processing ERA5: {year}-{month:02d}")
            try:
                nc_file = fetch_era5_month(year, month, ERA5_CACHE)
            except Exception as e:
                logger.error(f"ERA5 download failed {year}-{month:02d}: {e}")
                continue

            with get_conn() as conn:
                for spot in spots:
                    try:
                        records = extract_spot_timeseries(nc_file, spot["lat"], spot["lon"])
                    except Exception as e:
                        logger.error(f"ERA5 extract failed for {spot['id']}: {e}")
                        continue

                    inserted = 0
                    for r in records:
                        try:
                            conn.execute(
                                """
                                INSERT OR IGNORE INTO hourly_conditions
                                    (spot_id, timestamp,
                                     wave_height_m, wave_period_s, wave_direction_deg,
                                     swell_height_m, swell_period_s, swell_direction_deg,
                                     wind_speed_ms, wind_direction_deg,
                                     tide_height_cm, moon_phase,
                                     data_source, is_forecast)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                                """,
                                (
                                    spot["id"], r["timestamp"],
                                    r.get("wave_height_m"), r.get("wave_period_s"), r.get("wave_direction_deg"),
                                    r.get("swell_height_m"), r.get("swell_period_s"), r.get("swell_direction_deg"),
                                    r.get("wind_speed_ms"), r.get("wind_direction_deg"),
                                    None, None,  # tide and moon added separately
                                    "era5", 0,
                                ),
                            )
                            inserted += conn.execute("SELECT changes()").fetchone()[0]
                        except Exception as e:
                            logger.debug(f"Insert skip: {e}")

                    conn.commit()
                    total_inserted += inserted

            logger.info(f"  Inserted {total_inserted} rows so far")

    logger.info(f"ERA5 backfill complete. Total rows inserted: {total_inserted}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-year", type=int, default=1990)
    parser.add_argument("--end-year", type=int, default=2024)
    args = parser.parse_args()
    backfill(args.start_year, args.end_year)
