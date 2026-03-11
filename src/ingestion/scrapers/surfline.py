"""Surfline public mapview API scraper.

Surfline exposes a public (no-auth) mapview JSON API that returns current
surf conditions for all spots within a geographic bounding box.

Endpoint:
    https://services.surfline.com/kbyg/mapview?south=24&north=45&west=130&east=145

Score mapping (conditions.value → normalized 0-1):
    FLAT          → 0.05
    VERY_POOR     → 0.10
    POOR          → 0.25
    POOR_TO_FAIR  → 0.40
    FAIR          → 0.60
    FAIR_TO_GOOD  → 0.75
    GOOD          → 0.85
    GOOD_TO_EPIC  → 0.95
    EPIC          → 1.00

Matching strategy:
    Surfline spot names/IDs don't map 1-to-1 to our spots.json.
    We match by nearest geographic distance (haversine), accepting
    pairs within MAX_MATCH_KM kilometres.
"""

import json
import logging
import math
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests

logger = logging.getLogger(__name__)

MAPVIEW_URL = (
    "https://services.surfline.com/kbyg/mapview"
    "?south=24&north=45&west=130&east=145"
)
MAX_MATCH_KM = 20.0      # max distance to accept a geo-match
REQUEST_TIMEOUT = 15     # seconds

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Referer": "https://www.surfline.com/",
}

SCORE_MAP: dict[str, float] = {
    "FLAT":          0.05,
    "VERY_POOR":     0.10,
    "POOR":          0.25,
    "POOR_TO_FAIR":  0.40,
    "FAIR":          0.60,
    "FAIR_TO_GOOD":  0.75,
    "GOOD":          0.85,
    "GOOD_TO_EPIC":  0.95,
    "EPIC":          1.00,
}

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return great-circle distance in kilometres between two points."""
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _load_our_spots() -> list[dict]:
    """Load spots.json from the project data directory."""
    spots_path = Path(__file__).parents[3] / "data" / "spots.json"
    with open(spots_path, encoding="utf-8") as f:
        return json.load(f)


def _match_spot(surfline_lat: float, surfline_lon: float, our_spots: list[dict]) -> Optional[dict]:
    """Return the closest spot from our spots.json within MAX_MATCH_KM, or None."""
    best_spot = None
    best_dist = float("inf")
    for spot in our_spots:
        dist = _haversine_km(surfline_lat, surfline_lon, spot["lat"], spot["lon"])
        if dist < best_dist:
            best_dist = dist
            best_spot = spot
    if best_dist <= MAX_MATCH_KM:
        return best_spot
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fetch_current_conditions() -> list[dict]:
    """Fetch Surfline mapview API and return raw spot condition list.

    Returns:
        List of dicts from data.spots (raw Surfline format).
    """
    try:
        resp = requests.get(MAPVIEW_URL, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as e:
        logger.error(f"Surfline mapview fetch failed: {e}")
        return []

    try:
        payload = resp.json()
        return payload["data"]["spots"]
    except (KeyError, ValueError) as e:
        logger.error(f"Surfline JSON parse error: {e}")
        return []


def scrape_all_spots() -> list[dict]:
    """Fetch Surfline conditions and match to our spots.json.

    Returns:
        List of score observation dicts ready for DB insertion.
    """
    our_spots = _load_our_spots()
    surfline_spots = fetch_current_conditions()
    if not surfline_spots:
        logger.warning("Surfline: no spots returned from API")
        return []

    observed_at = datetime.utcnow().replace(minute=0, second=0, microsecond=0)
    results: list[dict] = []
    matched_our_ids: set[str] = set()  # prevent duplicate matches

    for sl_spot in surfline_spots:
        sl_lat = sl_spot.get("lat")
        sl_lon = sl_spot.get("lon")
        if sl_lat is None or sl_lon is None:
            continue

        conditions = sl_spot.get("conditions", {})
        rating_key = conditions.get("value") or sl_spot.get("rating", {}).get("key")
        if not rating_key:
            continue

        score_normalized = SCORE_MAP.get(rating_key)
        if score_normalized is None:
            logger.debug(f"Unknown Surfline rating key: {rating_key}")
            continue

        our_spot = _match_spot(sl_lat, sl_lon, our_spots)
        if our_spot is None:
            continue

        spot_id = our_spot["id"]
        if spot_id in matched_our_ids:
            # Already matched a closer Surfline spot to this spot_id
            continue
        matched_our_ids.add(spot_id)

        results.append({
            "spot_id":          spot_id,
            "source":           "surfline",
            "score_raw":        rating_key,
            "score_normalized": score_normalized,
            "observed_at":      observed_at.isoformat(),
            "surfline_name":    sl_spot.get("name", ""),
            "surfline_id":      sl_spot.get("_id", ""),
        })

    logger.info(
        f"Surfline: matched {len(results)}/{len(our_spots)} spots "
        f"(from {len(surfline_spots)} Surfline spots in Japan bbox)"
    )
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
                (
                    r["spot_id"],
                    r["source"],
                    r["score_raw"],
                    r["score_normalized"],
                    r["observed_at"],
                ),
            )
            inserted += conn.execute("SELECT changes()").fetchone()[0]
        except Exception as e:
            logger.error(f"DB insert error for {r['spot_id']}: {e}")
    conn.commit()
    return inserted


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    records = scrape_all_spots()
    print(f"\nMatched {len(records)} spots:")
    for r in records:
        print(
            f"  {r['spot_id']:30s} ← {r['surfline_name']:30s} "
            f"{r['score_raw']:15s} ({r['score_normalized']:.2f})"
        )
