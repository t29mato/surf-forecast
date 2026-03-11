"""Lightweight Surfline condition scraper.

Fetches current surf conditions from Surfline's public mapview API
and saves them to the SQLite DB as score_observations.

Run multiple times per day to accumulate training labels:
    python scripts/scrape_surfline.py

Exit codes:
    0  success (even if 0 records inserted — duplicates are silently skipped)
    1  fatal error (API unreachable, DB error, etc.)
"""

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.db.models import get_conn, init_db
from src.ingestion.scrapers.surfline import scrape_all_spots, save_scores

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> int:
    try:
        init_db()
    except Exception as e:
        logger.error(f"DB init failed: {e}")
        return 1

    records = scrape_all_spots()
    if not records:
        logger.warning("No Surfline records scraped — check API or spot matching")
        return 0

    try:
        with get_conn() as conn:
            inserted = save_scores(records, conn)
    except Exception as e:
        logger.error(f"DB save failed: {e}")
        return 1

    logger.info(f"Done: {inserted} new records inserted ({len(records)} fetched)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
