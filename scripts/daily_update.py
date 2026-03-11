"""Daily ETL orchestrator for surf forecast.

Runs every morning at 06:00 JST via GitHub Actions.

Steps:
    1. Scrape BCM + 波乗り道場 for today's scores
    2. Fetch today's conditions from Open-Meteo (historical/current)
    3. Fetch tide data from JMA
    4. Add moon phase to today's conditions
    5. Generate predictions JSON
    6. Log accuracy: yesterday's predictions vs today's actual scores

Usage:
    python scripts/daily_update.py
    python scripts/daily_update.py --dry-run   # no DB writes, no JSON output
"""

import argparse
import json
import logging
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.db.models import get_conn, init_db
from src.ingestion.scrapers import bcm, naminori_dojo, surfline
from src.ingestion.apis.open_meteo import fetch_historical
from src.ingestion.apis.jma_tide import fetch_tide_month, STATION_CODES
from src.ingestion.apis.moon_phase import get_moon_phase

logger = logging.getLogger(__name__)

SPOTS_JSON = Path(__file__).parent.parent / "data" / "spots.json"


def load_spots() -> list[dict]:
    return json.loads(SPOTS_JSON.read_text())


def step1_scrape_scores(dry_run: bool) -> int:
    """Scrape today's surf scores from BCM, 波乗り道場, and Surfline."""
    logger.info("=== Step 1: Scraping surf scores ===")
    bcm_records = bcm.scrape_all_spots()
    dojo_records = naminori_dojo.scrape_all_spots()
    surfline_records = surfline.scrape_all_spots()
    all_records = bcm_records + dojo_records + surfline_records
    logger.info(f"Scraped {len(all_records)} score records")

    if dry_run:
        return len(all_records)

    with get_conn() as conn:
        inserted = 0
        for r in all_records:
            try:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO score_observations
                        (spot_id, source, score_raw, score_normalized, observed_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (r["spot_id"], r["source"], r["score_raw"],
                     r["score_normalized"], r["observed_at"]),
                )
                inserted += conn.execute("SELECT changes()").fetchone()[0]
            except Exception as e:
                logger.warning(f"Score insert error: {e}")
        conn.commit()

    logger.info(f"  Inserted {inserted} new score records")
    return inserted


def step2_fetch_conditions(spots: list[dict], dry_run: bool) -> int:
    """Fetch today's (and yesterday's) conditions from Open-Meteo."""
    logger.info("=== Step 2: Fetching environmental conditions ===")
    today = date.today()
    yesterday = today - timedelta(days=1)

    total_inserted = 0
    for spot in spots:
        logger.debug(f"  Fetching conditions for {spot['id']}")
        try:
            records = fetch_historical(spot["lat"], spot["lon"], yesterday, today)
        except Exception as e:
            logger.warning(f"Open-Meteo failed for {spot['id']}: {e}")
            continue

        if dry_run:
            total_inserted += len(records)
            continue

        with get_conn() as conn:
            for r in records:
                # Add moon phase
                ts = datetime.fromisoformat(r["timestamp"])
                moon = get_moon_phase(ts)

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
                            None, moon,
                            "open_meteo", 0,
                        ),
                    )
                    total_inserted += conn.execute("SELECT changes()").fetchone()[0]
                except Exception as e:
                    logger.debug(f"Condition insert skip: {e}")
            conn.commit()

    logger.info(f"  Inserted {total_inserted} condition records")
    return total_inserted


def step3_accuracy_log():
    """Log yesterday's prediction accuracy vs today's actual scores."""
    logger.info("=== Step 3: Accuracy logging ===")
    yesterday = (datetime.now() - timedelta(days=1)).date()

    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT p.spot_id,
                   AVG(ABS(p.predicted_score - so.score_normalized)) AS mae,
                   COUNT(*) AS n
            FROM predictions p
            JOIN score_observations so ON (
                p.spot_id = so.spot_id
                AND date(p.forecast_timestamp) = date(so.observed_at)
            )
            WHERE date(p.forecast_timestamp) = ?
              AND so.source IN ('bcm', 'naminori_dojo', 'surfline')
            GROUP BY p.spot_id
            """,
            (str(yesterday),),
        ).fetchall()

    if not rows:
        logger.info("  No accuracy data available yet")
        return

    maes = [r["mae"] for r in rows if r["mae"] is not None]
    if maes:
        overall = sum(maes) / len(maes)
        logger.info(f"  Overall MAE (yesterday): {overall:.4f} across {len(rows)} spots")
    for row in rows:
        logger.info(f"  {row['spot_id']}: MAE={row['mae']:.4f} (n={row['n']})")


def run(dry_run: bool = False):
    init_db()
    spots = load_spots()
    logger.info(f"Loaded {len(spots)} spots")

    step1_scrape_scores(dry_run)
    step2_fetch_conditions(spots, dry_run)
    step3_accuracy_log()

    if not dry_run:
        # Trigger prediction generation
        import subprocess
        result = subprocess.run(
            [sys.executable, "scripts/generate_predictions.py"],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            logger.error(f"generate_predictions failed: {result.stderr}")
        else:
            logger.info("Predictions updated successfully")

    logger.info("Daily update complete")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="No DB writes or file output")
    args = parser.parse_args()
    run(dry_run=args.dry_run)
