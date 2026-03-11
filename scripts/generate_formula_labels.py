"""Generate surf score labels from the formula for all historical conditions.

This creates training labels from existing ERA5/Open-Meteo conditions in the DB,
using the score_formula.py calculation. Run this after backfill_era5.py.

Usage:
    python scripts/generate_formula_labels.py
    python scripts/generate_formula_labels.py --spot-id ichinomiya  # single spot
"""

import argparse
import json
import logging
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.db.models import get_conn, init_db
from src.processing.score_formula import compute_score

logger = logging.getLogger(__name__)
SPOTS_JSON = Path(__file__).parent.parent / "data" / "spots.json"


def generate_labels(spot_id_filter: str = None):
    init_db()
    spots = json.loads(SPOTS_JSON.read_text())

    if spot_id_filter:
        spots = [s for s in spots if s["id"] == spot_id_filter]

    total = 0
    for spot in spots:
        sid = spot["id"]
        logger.info(f"Generating formula labels for: {sid}")

        with get_conn() as conn:
            # Check what's already labeled
            existing = conn.execute(
                "SELECT COUNT(*) FROM score_observations WHERE spot_id = ? AND source = 'formula'",
                (sid,),
            ).fetchone()[0]

            # Load conditions for this spot (not yet labeled)
            cond_df = pd.read_sql_query(
                """
                SELECT hc.timestamp, hc.wave_height_m, hc.wave_period_s,
                       hc.swell_direction_deg, hc.wind_speed_ms, hc.wind_direction_deg,
                       hc.tide_height_cm
                FROM hourly_conditions hc
                WHERE hc.spot_id = ?
                  AND hc.is_forecast = 0
                ORDER BY hc.timestamp
                """,
                conn,
                params=(sid,),
            )

        if cond_df.empty:
            logger.warning(f"No conditions found for {sid}")
            continue

        logger.info(f"  {sid}: {len(cond_df)} rows of conditions, {existing} already labeled")

        inserted = 0
        with get_conn() as conn:
            for _, row in cond_df.iterrows():
                score = compute_score(
                    wave_height_m=row.get("wave_height_m"),
                    wave_period_s=row.get("wave_period_s"),
                    swell_direction_deg=row.get("swell_direction_deg"),
                    spot_orientation_deg=spot.get("orientation_deg"),
                    wind_speed_ms=row.get("wind_speed_ms"),
                    wind_direction_deg=row.get("wind_direction_deg"),
                    tide_height_cm=row.get("tide_height_cm"),
                    optimal_wave_height_m=spot.get("optimal_wave_height_m", 1.2),
                    break_type=spot.get("break_type", "beach"),
                )
                if score is None:
                    continue

                try:
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO score_observations
                            (spot_id, source, score_raw, score_normalized, observed_at)
                        VALUES (?, 'formula', 'formula', ?, ?)
                        """,
                        (sid, score, row["timestamp"]),
                    )
                    inserted += conn.execute("SELECT changes()").fetchone()[0]
                except Exception as e:
                    logger.debug(f"Skip: {e}")

            conn.commit()

        total += inserted
        logger.info(f"  {sid}: inserted {inserted} formula labels")

    logger.info(f"Done. Total formula labels inserted: {total}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--spot-id", default=None, help="Process only this spot ID")
    args = parser.parse_args()
    generate_labels(spot_id_filter=args.spot_id)
