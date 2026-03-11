"""Generate hourly surf score predictions for all spots and export as JSON.

Fetches 7-day forecast from Open-Meteo, applies the trained LightGBM model,
and writes the results to web/public/data/predictions.json.

If no trained model exists, falls back to the score_formula.py rule-based method.

Usage:
    python scripts/generate_predictions.py
    python scripts/generate_predictions.py --days 7
"""

import argparse
import json
import logging
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.preprocessing import LabelEncoder

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.db.models import get_conn, init_db
from src.ingestion.apis.open_meteo import fetch_forecast
from src.ingestion.apis.moon_phase import get_moon_phase
from src.processing.features import build_features, get_feature_columns
from src.processing.score_formula import compute_score, score_to_label

logger = logging.getLogger(__name__)

SPOTS_JSON = Path(__file__).parent.parent / "data" / "spots.json"
OUTPUT_JSON = Path(__file__).parent.parent / "web" / "public" / "data" / "predictions.json"
MODEL_DIR = Path(__file__).parent.parent / "data" / "models"


def load_model_if_available():
    """Try to load the trained model; return None if not available."""
    try:
        from src.models.train import load_latest_model
        model, meta = load_latest_model()
        logger.info(f"Using trained model: {meta['version']} (test MAE: {meta.get('test_mae', '?'):.4f})")
        return model, meta
    except FileNotFoundError:
        logger.info("No trained model found. Using rule-based formula.")
        return None, None


def predict_with_model(
    model,
    meta: dict,
    conditions_df: pd.DataFrame,
    spot: dict,
) -> list[float]:
    """Apply ML model to forecast conditions."""
    feats = build_features(conditions_df, spot)
    feature_cols = meta["feature_columns"]

    # Encode spot_id
    le_classes = meta["spot_label_encoder"]
    le = LabelEncoder()
    le.classes_ = np.array(le_classes)

    if spot["id"] in le_classes:
        feats["spot_id_enc"] = le.transform([spot["id"]] * len(feats))
    else:
        feats["spot_id_enc"] = 0  # unseen spot: fallback to 0

    X = feats[feature_cols].astype(float)
    preds = model.predict(X)
    return list(np.clip(preds, 0, 1))


def predict_with_formula(conditions_df: pd.DataFrame, spot: dict) -> list[float]:
    """Apply rule-based formula to forecast conditions."""
    scores = []
    for _, row in conditions_df.iterrows():
        s = compute_score(
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
        scores.append(s if s is not None else 0.0)
    return scores


def generate(days: int = 7):
    init_db()
    spots = json.loads(SPOTS_JSON.read_text())
    model, meta = load_model_if_available()

    all_predictions = {}
    generated_at = datetime.now().isoformat()

    for spot in spots:
        sid = spot["id"]
        logger.info(f"Generating predictions for {sid}")

        try:
            forecast_records = fetch_forecast(spot["lat"], spot["lon"], days=days)
        except Exception as e:
            logger.warning(f"Forecast fetch failed for {sid}: {e}")
            continue

        if not forecast_records:
            continue

        conditions_df = pd.DataFrame(forecast_records)
        conditions_df["timestamp"] = pd.to_datetime(conditions_df["timestamp"])

        # Add moon phase
        conditions_df["moon_phase"] = conditions_df["timestamp"].apply(
            lambda ts: get_moon_phase(ts.to_pydatetime())
        )

        # Predict
        if model is not None:
            scores = predict_with_model(model, meta, conditions_df, spot)
        else:
            scores = predict_with_formula(conditions_df, spot)

        # Build hourly output
        hourly = []
        for i, (_, row) in enumerate(conditions_df.iterrows()):
            score = scores[i]
            hourly.append({
                "timestamp": row["timestamp"].isoformat(),
                "score": round(float(score), 3),
                "label": score_to_label(score),
                "wave_height_m": row.get("wave_height_m"),
                "wave_period_s": row.get("wave_period_s"),
                "swell_height_m": row.get("swell_height_m"),
                "wind_speed_ms": row.get("wind_speed_ms"),
                "wind_direction_deg": row.get("wind_direction_deg"),
            })

        # Save to DB
        with get_conn() as conn:
            model_version = meta["version"] if meta else "formula"
            for h in hourly:
                try:
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO predictions
                            (spot_id, forecast_timestamp, predicted_score, model_version)
                        VALUES (?, ?, ?, ?)
                        """,
                        (sid, h["timestamp"], h["score"], model_version),
                    )
                except Exception as e:
                    logger.debug(f"Prediction insert error: {e}")
            conn.commit()

        # Summary per day for JSON output
        daily_summary = {}
        for h in hourly:
            day = h["timestamp"][:10]
            if day not in daily_summary:
                daily_summary[day] = []
            daily_summary[day].append(h["score"])

        all_predictions[sid] = {
            "spot": {
                "id": sid,
                "name": spot["name"],
                "prefecture": spot["prefecture"],
                "region": spot["region"],
                "lat": spot["lat"],
                "lon": spot["lon"],
                "break_type": spot.get("break_type"),
            },
            "hourly": hourly,
            "daily_max": {
                day: round(max(scores_list), 3)
                for day, scores_list in daily_summary.items()
            },
            "best_time_7d": max(hourly, key=lambda h: h["score"])["timestamp"],
        }

    # Write output JSON
    output = {
        "generated_at": generated_at,
        "model_version": meta["version"] if meta else "formula",
        "forecast_days": days,
        "spots": all_predictions,
    }

    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(json.dumps(output, ensure_ascii=False, indent=2))
    logger.info(f"Predictions written to {OUTPUT_JSON}")
    logger.info(f"  {len(all_predictions)} spots, {days} days forecast")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=7)
    args = parser.parse_args()
    generate(days=args.days)
