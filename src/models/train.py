"""LightGBM + Optuna training pipeline for surf score prediction.

Flow:
    1. Load training data from SQLite (score_observations JOIN hourly_conditions)
    2. Build feature matrix via features.py
    3. Time-series train/valid/test split
    4. Optuna hyperparameter tuning (50 trials)
    5. Save best model to data/models/
    6. Print accuracy report per spot

Usage:
    python -m src.models.train [--label-source formula|scraped|all]
"""

import argparse
import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path

import joblib
import lightgbm as lgb
import numpy as np
import optuna
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.preprocessing import LabelEncoder

from src.db.models import get_conn, DB_PATH
from src.processing.features import build_features, get_feature_columns

logger = logging.getLogger(__name__)

MODEL_DIR = Path(__file__).parent.parent.parent / "data" / "models"
SPOTS_JSON = Path(__file__).parent.parent.parent / "data" / "spots.json"

optuna.logging.set_verbosity(optuna.logging.WARNING)


# ──────────────────────────────────────────────
# Data loading
# ──────────────────────────────────────────────

def load_training_data(label_source: str = "all") -> pd.DataFrame:
    """Load (features, labels) from DB and join conditions with scores.

    Args:
        label_source: 'formula' = only formula-generated labels
                      'scraped' = only BCM/naminori scraped labels
                      'all' = use all available, scraped preferred when available

    Returns:
        DataFrame with features + 'score' column
    """
    spots = json.loads(SPOTS_JSON.read_text())
    spot_map = {s["id"]: s for s in spots}

    with get_conn() as conn:
        # Load all scores
        if label_source == "formula":
            source_filter = "AND source = 'formula'"
        elif label_source == "scraped":
            source_filter = "AND source IN ('bcm', 'naminori_dojo')"
        else:
            source_filter = ""

        scores_df = pd.read_sql_query(
            f"""
            SELECT spot_id, score_normalized, observed_at, source
            FROM score_observations
            WHERE score_normalized IS NOT NULL
            {source_filter}
            ORDER BY observed_at
            """,
            conn,
        )

        conditions_df = pd.read_sql_query(
            """
            SELECT *
            FROM hourly_conditions
            ORDER BY spot_id, timestamp
            """,
            conn,
        )

    if scores_df.empty or conditions_df.empty:
        logger.error("No training data found. Run backfill scripts first.")
        return pd.DataFrame()

    # Merge scores to nearest hour of conditions
    scores_df["observed_at"] = pd.to_datetime(scores_df["observed_at"]).dt.floor("h")
    conditions_df["timestamp"] = pd.to_datetime(conditions_df["timestamp"])

    # Build features per spot, then merge with scores
    all_rows = []
    for spot_id, spot in spot_map.items():
        cond = conditions_df[conditions_df["spot_id"] == spot_id].copy()
        if cond.empty:
            continue

        feats = build_features(cond, spot)
        feats["timestamp"] = cond["timestamp"].values

        # Get scores for this spot
        spot_scores = scores_df[scores_df["spot_id"] == spot_id].copy()
        spot_scores = spot_scores.rename(columns={"observed_at": "timestamp"})

        merged = feats.merge(
            spot_scores[["timestamp", "score_normalized"]],
            on="timestamp",
            how="inner",
        )
        if not merged.empty:
            all_rows.append(merged)

    if not all_rows:
        logger.error("No rows after joining features with scores.")
        return pd.DataFrame()

    df = pd.concat(all_rows, ignore_index=True)
    logger.info(f"Training data: {len(df)} rows across {df['spot_id'].nunique()} spots")
    return df


# ──────────────────────────────────────────────
# Training
# ──────────────────────────────────────────────

def train(label_source: str = "all", n_trials: int = 50):
    """Full training pipeline."""
    df = load_training_data(label_source)
    if df.empty:
        return

    # Encode spot_id
    le = LabelEncoder()
    df["spot_id_enc"] = le.fit_transform(df["spot_id"])

    feature_cols = get_feature_columns(df)
    feature_cols = [c for c in feature_cols if c not in ("score_normalized", "spot_id_enc")]
    feature_cols.append("spot_id_enc")

    X = df[feature_cols].astype(float)
    y = df["score_normalized"]

    # Time-series split
    df_sorted = df.sort_values("timestamp")
    n = len(df_sorted)
    train_end = int(n * 0.70)
    valid_end = int(n * 0.85)

    idx = df_sorted.index
    X_train = X.loc[idx[:train_end]]
    y_train = y.loc[idx[:train_end]]
    X_valid = X.loc[idx[train_end:valid_end]]
    y_valid = y.loc[idx[train_end:valid_end]]
    X_test  = X.loc[idx[valid_end:]]
    y_test  = y.loc[idx[valid_end:]]

    logger.info(f"Train: {len(X_train)}, Valid: {len(X_valid)}, Test: {len(X_test)}")

    # Optuna objective
    def objective(trial: optuna.Trial) -> float:
        params = {
            "objective": "regression",
            "metric": "mae",
            "verbosity": -1,
            "boosting_type": "gbdt",
            "num_leaves": trial.suggest_int("num_leaves", 15, 127),
            "max_depth": trial.suggest_int("max_depth", 3, 12),
            "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.2, log=True),
            "n_estimators": trial.suggest_int("n_estimators", 200, 1000),
            "min_child_samples": trial.suggest_int("min_child_samples", 5, 50),
            "subsample": trial.suggest_float("subsample", 0.6, 1.0),
            "colsample_bytree": trial.suggest_float("colsample_bytree", 0.6, 1.0),
            "reg_alpha": trial.suggest_float("reg_alpha", 1e-4, 1.0, log=True),
            "reg_lambda": trial.suggest_float("reg_lambda", 1e-4, 1.0, log=True),
        }
        model = lgb.LGBMRegressor(**params)
        model.fit(
            X_train, y_train,
            eval_set=[(X_valid, y_valid)],
            callbacks=[lgb.early_stopping(50, verbose=False), lgb.log_evaluation(-1)],
        )
        preds = model.predict(X_valid)
        return mean_absolute_error(y_valid, preds)

    study = optuna.create_study(direction="minimize")
    study.optimize(objective, n_trials=n_trials, show_progress_bar=True)

    best_params = study.best_params
    best_params.update({
        "objective": "regression",
        "metric": "mae",
        "verbosity": -1,
        "boosting_type": "gbdt",
    })

    # Train final model with best params
    final_model = lgb.LGBMRegressor(**best_params)
    final_model.fit(
        pd.concat([X_train, X_valid]),
        pd.concat([y_train, y_valid]),
    )

    # Evaluate on test set
    test_preds = np.clip(final_model.predict(X_test), 0, 1)
    mae = mean_absolute_error(y_test, test_preds)
    rmse = float(np.sqrt(mean_squared_error(y_test, test_preds)))
    r2 = r2_score(y_test, test_preds)

    print(f"\n=== Test Results ===")
    print(f"MAE:  {mae:.4f}")
    print(f"RMSE: {rmse:.4f}")
    print(f"R²:   {r2:.4f}")

    # Per-spot accuracy
    test_df = df.loc[idx[valid_end:]].copy()
    test_df["predicted"] = test_preds
    print("\n=== Per-spot MAE ===")
    for spot_id, grp in test_df.groupby("spot_id"):
        spot_mae = mean_absolute_error(grp["score_normalized"], grp["predicted"])
        print(f"  {spot_id}: {spot_mae:.4f} (n={len(grp)})")

    # Save model and metadata
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    version = datetime.now().strftime("%Y%m%d_%H%M")
    model_path = MODEL_DIR / f"surf_lgbm_{version}.joblib"
    meta_path = MODEL_DIR / f"surf_lgbm_{version}_meta.json"

    joblib.dump(final_model, model_path)

    meta = {
        "version": version,
        "label_source": label_source,
        "feature_columns": feature_cols,
        "spot_label_encoder": list(le.classes_),
        "test_mae": mae,
        "test_rmse": rmse,
        "test_r2": r2,
        "best_params": best_params,
        "trained_at": datetime.now().isoformat(),
        "n_train": len(X_train),
        "n_valid": len(X_valid),
        "n_test": len(X_test),
    }
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False))

    # Also save as "latest"
    joblib.dump(final_model, MODEL_DIR / "surf_lgbm_latest.joblib")
    (MODEL_DIR / "surf_lgbm_latest_meta.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False)
    )

    print(f"\nModel saved: {model_path}")
    return final_model, meta


def load_latest_model():
    """Load the latest trained model and its metadata."""
    model_path = MODEL_DIR / "surf_lgbm_latest.joblib"
    meta_path = MODEL_DIR / "surf_lgbm_latest_meta.json"

    if not model_path.exists():
        raise FileNotFoundError(f"No model found at {model_path}. Run train.py first.")

    model = joblib.load(model_path)
    meta = json.loads(meta_path.read_text())
    return model, meta


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--label-source",
        choices=["formula", "scraped", "all"],
        default="all",
        help="Which label source to use for training",
    )
    parser.add_argument(
        "--n-trials",
        type=int,
        default=50,
        help="Number of Optuna hyperparameter tuning trials",
    )
    args = parser.parse_args()
    train(label_source=args.label_source, n_trials=args.n_trials)
