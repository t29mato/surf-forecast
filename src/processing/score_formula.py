"""Surf score calculation formula.

Used to generate training labels from historical wave conditions (ERA5 data)
before real BCM/scraping scores accumulate.

Based on well-known surf quality assessment factors used by Surfline, MSW, etc.

Score range: 0.0 (worst) to 1.0 (best, like ◎ on BCM)
"""

import math
import numpy as np
import pandas as pd
from typing import Optional


def _gaussian(x: float, mean: float, sigma: float) -> float:
    """Gaussian curve: peaks at mean, decays with sigma."""
    return math.exp(-0.5 * ((x - mean) / sigma) ** 2)


def compute_score(
    wave_height_m: Optional[float],
    wave_period_s: Optional[float],
    swell_direction_deg: Optional[float],
    spot_orientation_deg: Optional[float],
    wind_speed_ms: Optional[float],
    wind_direction_deg: Optional[float],
    tide_height_cm: Optional[float] = None,
    optimal_wave_height_m: float = 1.2,
    break_type: str = "beach",
) -> Optional[float]:
    """Compute a surf quality score from wave/wind/tide conditions.

    Args:
        wave_height_m: Significant wave height in meters
        wave_period_s: Mean wave period in seconds
        swell_direction_deg: Direction swell is coming FROM (meteorological convention)
        spot_orientation_deg: Direction the spot faces (e.g., 90 = East-facing)
        wind_speed_ms: Wind speed in m/s
        wind_direction_deg: Wind direction (coming FROM, degrees)
        tide_height_cm: Tidal height in cm (optional)
        optimal_wave_height_m: Best wave height for this spot
        break_type: 'beach' | 'reef' | 'point'

    Returns:
        Score 0.0–1.0, or None if insufficient data
    """
    if wave_height_m is None or wave_period_s is None:
        return None

    # --- 1. Wave height score ---
    # Gaussian centered at optimal height; beach breaks more forgiving than reef
    sigma = 0.6 if break_type == "beach" else 0.4
    height_score = _gaussian(wave_height_m, optimal_wave_height_m, sigma)
    # Very small waves (<0.3m) are unsurfable regardless
    if wave_height_m < 0.3:
        height_score *= 0.1

    # --- 2. Wave period score ---
    # Longer period = more powerful, better shape. Peaks at 12s+
    # Formula: tanh curve, 5s→0.2, 8s→0.6, 12s→0.9, 15s+→1.0
    period_score = math.tanh((wave_period_s - 4) / 5)
    period_score = max(0.0, period_score)

    # --- 3. Swell-spot alignment score ---
    alignment_score = 1.0  # default if no direction info
    if swell_direction_deg is not None and spot_orientation_deg is not None:
        # Swell "coming FROM" direction; spot faces spot_orientation_deg.
        # Ideal: swell coming from direction opposite to spot face.
        # e.g., East-facing spot (90°) → ideal swell from East (90° from)
        # Angle between "where swell goes" and spot orientation
        swell_going_deg = (swell_direction_deg + 180) % 360
        angle_diff = abs(swell_going_deg - spot_orientation_deg)
        if angle_diff > 180:
            angle_diff = 360 - angle_diff
        # 0° = perfect alignment, 90° = side swell, 180° = opposite
        alignment_score = math.cos(math.radians(angle_diff))
        alignment_score = max(0.0, alignment_score)

    # --- 4. Wind score ---
    wind_score = 0.8  # default (calm) if no data
    if wind_speed_ms is not None:
        if wind_direction_deg is not None and spot_orientation_deg is not None:
            # Offshore wind is best: blowing away from shore
            # Offshore = wind coming from land side (opposite to spot face)
            offshore_dir = (spot_orientation_deg + 180) % 360
            wind_angle = abs(wind_direction_deg - offshore_dir)
            if wind_angle > 180:
                wind_angle = 360 - wind_angle
            # 0° = perfect offshore, 90° = cross-shore, 180° = onshore
            offshore_factor = math.cos(math.radians(wind_angle))
            # Scale: offshore→1.0, cross→0.5, onshore→0.0
            wind_direction_score = (offshore_factor + 1) / 2
        else:
            wind_direction_score = 0.7

        # Wind speed penalty: light wind is best
        # <3 m/s: no penalty; 3-8 m/s: mild; >10 m/s: strong penalty
        if wind_speed_ms < 3:
            wind_speed_factor = 1.0
        elif wind_speed_ms < 8:
            wind_speed_factor = 1.0 - (wind_speed_ms - 3) / 10
        else:
            wind_speed_factor = max(0.2, 1.0 - wind_speed_ms / 15)

        wind_score = wind_direction_score * wind_speed_factor

    # --- 5. Tide score (optional) ---
    tide_score = 0.7  # neutral if no data
    if tide_height_cm is not None:
        # Most beach breaks prefer mid-tide.
        # Normalize 0-300cm → score peaks at 150cm.
        # This is very spot-dependent; tide_height_cm is normalized by station.
        # For now, prefer mid-tide (rough heuristic).
        tide_score = _gaussian(tide_height_cm, 150, 80)

    # --- Weighted combination ---
    # Weights reflect relative importance for surf quality
    weights = {
        "height": 0.30,
        "period": 0.25,
        "alignment": 0.20,
        "wind": 0.20,
        "tide": 0.05,
    }
    score = (
        weights["height"] * height_score
        + weights["period"] * period_score
        + weights["alignment"] * alignment_score
        + weights["wind"] * wind_score
        + weights["tide"] * tide_score
    )

    return float(np.clip(score, 0.0, 1.0))


def apply_to_dataframe(
    df: pd.DataFrame,
    spot_orientation_deg: float,
    optimal_wave_height_m: float,
    break_type: str = "beach",
) -> pd.Series:
    """Apply compute_score to each row of a conditions DataFrame.

    Expected columns: wave_height_m, wave_period_s, swell_direction_deg,
                      wind_speed_ms, wind_direction_deg, tide_height_cm (optional)
    """
    scores = []
    for _, row in df.iterrows():
        s = compute_score(
            wave_height_m=row.get("wave_height_m"),
            wave_period_s=row.get("wave_period_s"),
            swell_direction_deg=row.get("swell_direction_deg"),
            spot_orientation_deg=spot_orientation_deg,
            wind_speed_ms=row.get("wind_speed_ms"),
            wind_direction_deg=row.get("wind_direction_deg"),
            tide_height_cm=row.get("tide_height_cm"),
            optimal_wave_height_m=optimal_wave_height_m,
            break_type=break_type,
        )
        scores.append(s)
    return pd.Series(scores, index=df.index, name="score_formula")


def score_to_label(score: float) -> str:
    """Convert 0-1 score to BCM-style label."""
    if score >= 0.85:
        return "◎"
    elif score >= 0.65:
        return "○"
    elif score >= 0.40:
        return "△"
    else:
        return "×"


if __name__ == "__main__":
    # Example: Perfect conditions at a beach break
    s = compute_score(
        wave_height_m=1.5,
        wave_period_s=12.0,
        swell_direction_deg=90,    # swell from East
        spot_orientation_deg=90,   # East-facing spot
        wind_speed_ms=2.0,
        wind_direction_deg=270,    # West wind = offshore for East-facing
        tide_height_cm=150,
        optimal_wave_height_m=1.2,
    )
    print(f"Score: {s:.3f} → {score_to_label(s)}")
