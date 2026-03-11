"""BCM (ビーシーエム) surf score scraper.

BCM is one of Japan's most popular surf forecast sites.
This scraper collects today's surf scores for each spot.

Score mapping:
    ◎ (Excellent) → 1.0
    ○ (Good)      → 0.75
    △ (Fair)      → 0.5
    × (Poor)      → 0.25
    -- (No data)  → None
"""

import logging
import re
import time
from datetime import datetime, date
from typing import Optional

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

BCM_BASE_URL = "https://www.bcm.co.jp/sea/spot"
REQUEST_DELAY = 1.5  # seconds between requests

SCORE_MAP = {
    "◎": 1.0,
    "○": 0.75,
    "△": 0.5,
    "×": 0.25,
    "☓": 0.25,
    "--": None,
    "－－": None,
}

# Mapping from our spot IDs to BCM spot URL slugs / IDs
# These need to be verified against the actual BCM site structure
BCM_SPOT_URLS = {
    "oarai":       "https://www.bcm.co.jp/sea/spot/ibaraki/oarai/",
    "hasaki":      "https://www.bcm.co.jp/sea/spot/ibaraki/hasaki/",
    "ajigaura":    "https://www.bcm.co.jp/sea/spot/ibaraki/ajigaura/",
    "ichinomiya":  "https://www.bcm.co.jp/sea/spot/chiba/ichinomiya/",
    "shidashita":  "https://www.bcm.co.jp/sea/spot/chiba/shidashita/",
    "onjuku":      "https://www.bcm.co.jp/sea/spot/chiba/onjuku/",
    "katsuura":    "https://www.bcm.co.jp/sea/spot/chiba/katsuura/",
    "kujukuri":    "https://www.bcm.co.jp/sea/spot/chiba/kujukuri/",
    "tsurigasaki": "https://www.bcm.co.jp/sea/spot/chiba/tsurigasaki/",
    "kamakura":    "https://www.bcm.co.jp/sea/spot/kanagawa/kamakura/",
    "enoshima":    "https://www.bcm.co.jp/sea/spot/kanagawa/enoshima/",
    "chigasaki":   "https://www.bcm.co.jp/sea/spot/kanagawa/chigasaki/",
    "miyazaki_uchiumi":    "https://www.bcm.co.jp/sea/spot/miyazaki/uchiumi/",
    "miyazaki_kisakihama": "https://www.bcm.co.jp/sea/spot/miyazaki/kisakihama/",
    "kochi_tosa":  "https://www.bcm.co.jp/sea/spot/kochi/tosa/",
    "niijima":     "https://www.bcm.co.jp/sea/spot/tokyo/niijima/",
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ja,en;q=0.9",
}


def scrape_spot(spot_id: str, url: str) -> Optional[dict]:
    """Scrape BCM page for a single surf spot and return today's score.

    Args:
        spot_id: Our internal spot ID
        url: BCM spot page URL

    Returns:
        Dict with score data, or None if scraping failed
    """
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
    except requests.RequestException as e:
        logger.warning(f"BCM fetch failed for {spot_id}: {e}")
        return None

    soup = BeautifulSoup(resp.text, "lxml")
    observed_at = datetime.now().replace(minute=0, second=0, microsecond=0)

    # BCM shows today's score in a prominent element.
    # The exact CSS selectors depend on BCM's current HTML structure.
    # These selectors are best guesses — update after inspecting live pages.

    # Strategy 1: Look for score symbols in text
    score_raw, score_normalized = _extract_score_from_page(soup)

    if score_raw is None:
        logger.debug(f"No score found for {spot_id} on {url}")
        return None

    return {
        "spot_id": spot_id,
        "source": "bcm",
        "score_raw": score_raw,
        "score_normalized": score_normalized,
        "observed_at": observed_at.isoformat(),
        "url": url,
    }


def _extract_score_from_page(soup: BeautifulSoup) -> tuple[Optional[str], Optional[float]]:
    """Extract surf score from BCM page HTML.

    BCM uses Japanese score symbols (◎○△×).
    This searches for them in common locations.
    """
    # Try common score container selectors
    score_selectors = [
        ".score",
        ".surf-score",
        ".today-score",
        "[class*='score']",
        ".condition",
    ]

    for selector in score_selectors:
        els = soup.select(selector)
        for el in els:
            text = el.get_text(strip=True)
            for symbol, value in SCORE_MAP.items():
                if symbol in text:
                    return symbol, value

    # Fallback: search all text for score symbols
    full_text = soup.get_text()
    for symbol in ["◎", "○", "△", "×", "☓"]:
        if symbol in full_text:
            return symbol, SCORE_MAP[symbol]

    return None, None


def scrape_all_spots() -> list[dict]:
    """Scrape BCM scores for all configured spots.

    Returns:
        List of score observation dicts for insertion into DB
    """
    results = []
    for spot_id, url in BCM_SPOT_URLS.items():
        logger.info(f"Scraping BCM: {spot_id}")
        record = scrape_spot(spot_id, url)
        if record:
            results.append(record)
        time.sleep(REQUEST_DELAY)

    logger.info(f"BCM: scraped {len(results)}/{len(BCM_SPOT_URLS)} spots")
    return results


def save_scores(records: list[dict], conn) -> int:
    """Insert scraped scores into the DB, ignoring duplicates."""
    inserted = 0
    for r in records:
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
            logger.error(f"DB insert error for {r['spot_id']}: {e}")
    conn.commit()
    return inserted


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    records = scrape_all_spots()
    print(f"Scraped {len(records)} records:")
    for r in records:
        print(f"  {r['spot_id']}: {r['score_raw']} ({r['score_normalized']})")
