"""Feature engineering for surf score prediction.

Transforms raw hourly_conditions + spot metadata into ML-ready feature vectors.
"""

import math
import numpy as np
import pandas as pd
from typing import Optional


# ──────────────────────────────────────────────
# Cyclical encoding helpers
# ──────────────────────────────────────────────

def _sin_cos(value: float, period: float) -> tuple[float, float]:
    """Encode a cyclic value as (sin, cos) pair."""
    angle = 2 * math.pi * value / period
    return math.sin(angle), math.cos(angle)


# ──────────────────────────────────────────────
# Core feature builder
# ──────────────────────────────────────────────

def build_features(df: pd.DataFrame, spot: dict) -> pd.DataFrame:
    """Build ML feature matrix from a conditions DataFrame.

    Args:
        df: DataFrame with columns from hourly_conditions table.
            Must include 'timestamp' as datetime or string.
        spot: Dict with spot metadata (orientation_deg, optimal_wave_height_m,
              break_type, lat, lon)

    Returns:
        DataFrame with one row per hourly observation, feature columns only.
    """
    df = df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values("timestamp").reset_index(drop=True)

    orientation = spot.get("orientation_deg", 90)
    optimal_h = spot.get("optimal_wave_height_m", 1.2)

    feats = pd.DataFrame(index=df.index)

    # ── 1. Raw wave features ──
    feats["wave_height_m"] = df["wave_height_m"]
    feats["wave_period_s"] = df["wave_period_s"]
    feats["swell_height_m"] = df["swell_height_m"]
    feats["swell_period_s"] = df["swell_period_s"]
    feats["wind_speed_ms"] = df["wind_speed_ms"]
    feats["tide_height_cm"] = df.get("tide_height_cm", pd.Series(dtype=float))
    feats["moon_phase"] = df.get("moon_phase", pd.Series(dtype=float))

    # ── 2. Derived wave energy ──
    feats["swell_energy"] = (
        df["swell_height_m"].fillna(0) ** 2 * df["swell_period_s"].fillna(0)
    )
    feats["wave_energy"] = (
        df["wave_height_m"].fillna(0) ** 2 * df["wave_period_s"].fillna(0)
    )
    feats["wave_steepness"] = (
        df["wave_height_m"] / df["wave_period_s"].replace(0, np.nan)
    )
    feats["height_vs_optimal"] = df["wave_height_m"] - optimal_h

    # ── 3. Directional alignment (spot-relative) ──
    # Swell alignment: angle between swell and spot face
    feats["swell_alignment"] = df["swell_direction_deg"].apply(
        lambda d: _alignment_score(d, orientation) if pd.notna(d) else np.nan
    )
    # Wind: offshore vs onshore
    feats["wind_offshore_factor"] = df["wind_direction_deg"].apply(
        lambda d: _offshore_factor(d, orientation) if pd.notna(d) else np.nan
    )

    # Directional components (sin/cos) for wave & wind
    for col, period in [
        ("wave_direction_deg", 360),
        ("swell_direction_deg", 360),
        ("wind_direction_deg", 360),
    ]:
        if col in df.columns:
            feats[f"{col}_sin"] = df[col].apply(
                lambda d: math.sin(math.radians(d)) if pd.notna(d) else np.nan
            )
            feats[f"{col}_cos"] = df[col].apply(
                lambda d: math.cos(math.radians(d)) if pd.notna(d) else np.nan
            )

    # ── 4. Temporal features (cyclic) ──
    feats["hour_sin"] = df["timestamp"].apply(lambda t: math.sin(2 * math.pi * t.hour / 24))
    feats["hour_cos"] = df["timestamp"].apply(lambda t: math.cos(2 * math.pi * t.hour / 24))
    feats["month_sin"] = df["timestamp"].apply(lambda t: math.sin(2 * math.pi * t.month / 12))
    feats["month_cos"] = df["timestamp"].apply(lambda t: math.cos(2 * math.pi * t.month / 12))
    feats["day_of_year"] = df["timestamp"].dt.dayofyear

    # Tide phase (sin/cos) if available
    if "tide_height_cm" in df.columns and df["tide_height_cm"].notna().any():
        # Normalize tide to 0-1 range (assuming 0-400cm range)
        tide_norm = df["tide_height_cm"] / 400
        feats["tide_sin"] = tide_norm.apply(lambda t: math.sin(2 * math.pi * t) if pd.notna(t) else np.nan)
        feats["tide_cos"] = tide_norm.apply(lambda t: math.cos(2 * math.pi * t) if pd.notna(t) else np.nan)

    # Moon phase (sin/cos for 29.5-day cycle)
    if "moon_phase" in df.columns and df["moon_phase"].notna().any():
        feats["moon_sin"] = df["moon_phase"].apply(
            lambda p: math.sin(2 * math.pi * p) if pd.notna(p) else np.nan
        )
        feats["moon_cos"] = df["moon_phase"].apply(
            lambda p: math.cos(2 * math.pi * p) if pd.notna(p) else np.nan
        )

    # ── 5. Lag features (requires enough history) ──
    for lag_h in [1, 3, 6, 12, 24]:
        feats[f"wave_height_lag{lag_h}h"] = df["wave_height_m"].shift(lag_h)
        feats[f"wind_speed_lag{lag_h}h"] = df["wind_speed_ms"].shift(lag_h)

    # ── 6. Rolling window statistics ──
    for window_h in [3, 6, 12, 24]:
        feats[f"wave_height_roll{window_h}h_mean"] = (
            df["wave_height_m"].rolling(window_h, min_periods=1).mean()
        )
        feats[f"wind_speed_roll{window_h}h_mean"] = (
            df["wind_speed_ms"].rolling(window_h, min_periods=1).mean()
        )

    # Wave/wind change over 3h
    feats["wave_height_change_3h"] = df["wave_height_m"] - df["wave_height_m"].shift(3)
    feats["wind_speed_change_3h"] = df["wind_speed_ms"] - df["wind_speed_ms"].shift(3)

    # ── 7. Spot identifier (categorical) ──
    feats["spot_id"] = spot.get("id", "unknown")

    return feats


def _alignment_score(swell_dir_deg: float, spot_orientation_deg: float) -> float:
    """Return cosine similarity between swell travel direction and spot face.

    Returns 1.0 for perfect head-on swell, 0.0 for cross swell, -1 for opposite.
    """
    swell_going = (swell_dir_deg + 180) % 360
    diff = abs(swell_going - spot_orientation_deg)
    if diff > 180:
        diff = 360 - diff
    return math.cos(math.radians(diff))


def _offshore_factor(wind_dir_deg: float, spot_orientation_deg: float) -> float:
    """Return offshore factor: 1.0 = perfect offshore, -1.0 = onshore."""
    offshore_dir = (spot_orientation_deg + 180) % 360
    diff = abs(wind_dir_deg - offshore_dir)
    if diff > 180:
        diff = 360 - diff
    return math.cos(math.radians(diff))


def get_feature_columns(df: pd.DataFrame) -> list[str]:
    """Return list of numeric feature columns (exclude spot_id and timestamps)."""
    return [c for c in df.columns if c not in ("spot_id", "timestamp") and df[c].dtype != object]


if __name__ == "__main__":
    # Quick smoke test
    import json, sys
    from pathlib import Path

    spots = json.loads((Path(__file__).parent.parent.parent / "data/spots.json").read_text())
    spot = spots[0]

    # Fake one row of conditions
    fake = pd.DataFrame([{
        "timestamp": "2024-01-15 08:00",
        "wave_height_m": 1.5,
        "wave_period_s": 10.0,
        "wave_direction_deg": 95,
        "swell_height_m": 1.3,
        "swell_period_s": 11.0,
        "swell_direction_deg": 90,
        "wind_speed_ms": 3.0,
        "wind_direction_deg": 270,
        "tide_height_cm": 150.0,
        "moon_phase": 0.5,
    }])

    feats = build_features(fake, spot)
    print(f"Features: {list(feats.columns)}")
    print(feats.T)
