"""波乗り道場 (Naminori Dojo) surf score scraper.

波乗り道場 is a popular Japanese surf forecast site with more detailed conditions.
Scores are typically on a 1-10 or letter grade scale.

URL pattern: https://www.naminori.jp/surf/spot/<spot_id>/
"""

import logging
import re
import time
from datetime import datetime
from typing import Optional

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

REQUEST_DELAY = 1.5

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ja,en;q=0.9",
}

# Mapping from our spot IDs to 波乗り道場 spot URLs
# These need to be verified against the actual site structure
NAMINORI_SPOT_URLS = {
    "oarai":       "https://www.naminori.jp/surf/ibaraki/oarai/",
    "hasaki":      "https://www.naminori.jp/surf/ibaraki/hasaki/",
    "ichinomiya":  "https://www.naminori.jp/surf/chiba/ichinomiya/",
    "shidashita":  "https://www.naminori.jp/surf/chiba/shida/",
    "onjuku":      "https://www.naminori.jp/surf/chiba/onjuku/",
    "kujukuri":    "https://www.naminori.jp/surf/chiba/kujukuri/",
    "tsurigasaki": "https://www.naminori.jp/surf/chiba/tsurigasaki/",
    "kamakura":    "https://www.naminori.jp/surf/kanagawa/kamakura/",
    "chigasaki":   "https://www.naminori.jp/surf/kanagawa/chigasaki/",
    "miyazaki_kisakihama": "https://www.naminori.jp/surf/miyazaki/kisakihama/",
    "kochi_tosa":  "https://www.naminori.jp/surf/kochi/tosa/",
}

# Score normalization for 波乗り道場
# Site may use numeric (1-10) or grade (S/A/B/C/D) scales
GRADE_MAP = {
    "S": 1.0,
    "A": 0.85,
    "B": 0.65,
    "C": 0.45,
    "D": 0.25,
    "E": 0.1,
}


def _normalize_score(raw: str) -> Optional[float]:
    """Normalize raw score to 0.0-1.0 range."""
    raw = raw.strip()

    # Grade scale
    if raw.upper() in GRADE_MAP:
        return GRADE_MAP[raw.upper()]

    # Numeric scale 1-10
    try:
        val = float(raw)
        if 1 <= val <= 10:
            return (val - 1) / 9.0
        if 0 <= val <= 5:
            return val / 5.0
    except ValueError:
        pass

    # BCM-style symbols
    bcm_map = {"◎": 1.0, "○": 0.75, "△": 0.5, "×": 0.25}
    for symbol, value in bcm_map.items():
        if symbol in raw:
            return value

    return None


def scrape_spot(spot_id: str, url: str) -> Optional[dict]:
    """Scrape 波乗り道場 for a single surf spot."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
    except requests.RequestException as e:
        logger.warning(f"Naminori Dojo fetch failed for {spot_id}: {e}")
        return None

    soup = BeautifulSoup(resp.text, "lxml")
    observed_at = datetime.now().replace(minute=0, second=0, microsecond=0)

    score_raw, score_normalized = _extract_score(soup)

    if score_raw is None:
        logger.debug(f"No score found for {spot_id} on {url}")
        return None

    return {
        "spot_id": spot_id,
        "source": "naminori_dojo",
        "score_raw": score_raw,
        "score_normalized": score_normalized,
        "observed_at": observed_at.isoformat(),
        "url": url,
    }


def _extract_score(soup: BeautifulSoup) -> tuple[Optional[str], Optional[float]]:
    """Extract score from 波乗り道場 page."""
    # Try common selectors
    selectors = [
        ".score", ".surf-score", ".today", ".condition-score",
        "[class*='score']", "[class*='grade']",
    ]

    for selector in selectors:
        for el in soup.select(selector):
            text = el.get_text(strip=True)
            if not text:
                continue
            normalized = _normalize_score(text)
            if normalized is not None:
                return text, normalized

    # Search for grade patterns in page text
    text = soup.get_text()
    # Look for patterns like "コンディション: B" or "評価: 7"
    patterns = [
        r"コンディション[:\s：]*([SABCDE])",
        r"評価[:\s：]*(\d+(?:\.\d+)?)",
        r"スコア[:\s：]*(\d+(?:\.\d+)?)",
    ]
    for pattern in patterns:
        m = re.search(pattern, text)
        if m:
            raw = m.group(1)
            normalized = _normalize_score(raw)
            if normalized is not None:
                return raw, normalized

    return None, None


def scrape_all_spots() -> list[dict]:
    """Scrape 波乗り道場 scores for all configured spots."""
    results = []
    for spot_id, url in NAMINORI_SPOT_URLS.items():
        logger.info(f"Scraping Naminori Dojo: {spot_id}")
        record = scrape_spot(spot_id, url)
        if record:
            results.append(record)
        time.sleep(REQUEST_DELAY)

    logger.info(f"Naminori Dojo: scraped {len(results)}/{len(NAMINORI_SPOT_URLS)} spots")
    return results


def save_scores(records: list[dict], conn) -> int:
    """Insert scores into DB."""
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
    for r in records:
        print(f"  {r['spot_id']}: {r['score_raw']} ({r['score_normalized']})")
