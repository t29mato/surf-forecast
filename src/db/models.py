"""SQLite schema and database helpers for surf forecast."""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent.parent / "data" / "surf_forecast.db"


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db():
    """Create all tables if they don't exist."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS spots (
                id                    TEXT PRIMARY KEY,
                name                  TEXT NOT NULL,
                prefecture            TEXT NOT NULL,
                region                TEXT NOT NULL,
                lat                   REAL NOT NULL,
                lon                   REAL NOT NULL,
                orientation_deg       REAL,        -- スポットが向く方向（度）例: 90=東
                break_type            TEXT,        -- 'beach'|'reef'|'point'
                optimal_wave_height_m REAL,        -- 最適波高（m）
                nearest_tide_station  TEXT         -- JMA潮位観測所名
            );

            CREATE TABLE IF NOT EXISTS score_observations (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                spot_id          TEXT NOT NULL REFERENCES spots(id),
                source           TEXT NOT NULL,   -- 'bcm'|'naminori_dojo'|'formula'
                score_raw        TEXT,            -- 生スコア文字列
                score_normalized REAL NOT NULL,   -- 0.0〜1.0
                observed_at      DATETIME NOT NULL,
                scraped_at       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS hourly_conditions (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                spot_id             TEXT NOT NULL REFERENCES spots(id),
                timestamp           DATETIME NOT NULL,
                -- 波浪
                wave_height_m       REAL,
                wave_period_s       REAL,
                wave_direction_deg  REAL,
                -- うねり（スウェル）
                swell_height_m      REAL,
                swell_period_s      REAL,
                swell_direction_deg REAL,
                -- 風
                wind_speed_ms       REAL,
                wind_direction_deg  REAL,
                -- 潮位・月齢
                tide_height_cm      REAL,
                moon_phase          REAL,          -- 0.0=新月 0.5=満月 1.0=新月
                -- メタ
                data_source         TEXT NOT NULL, -- 'era5'|'open_meteo'
                is_forecast         INTEGER NOT NULL DEFAULT 0,
                UNIQUE(spot_id, timestamp, data_source)
            );

            CREATE TABLE IF NOT EXISTS predictions (
                id                 INTEGER PRIMARY KEY AUTOINCREMENT,
                spot_id            TEXT NOT NULL REFERENCES spots(id),
                forecast_timestamp DATETIME NOT NULL,
                predicted_score    REAL NOT NULL,  -- 0.0〜1.0
                confidence_lower   REAL,
                confidence_upper   REAL,
                model_version      TEXT,
                generated_at       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(spot_id, forecast_timestamp, model_version)
            );

            CREATE INDEX IF NOT EXISTS idx_hourly_spot_ts
                ON hourly_conditions(spot_id, timestamp);

            CREATE INDEX IF NOT EXISTS idx_obs_spot_ts
                ON score_observations(spot_id, observed_at);

            CREATE INDEX IF NOT EXISTS idx_pred_spot_ts
                ON predictions(spot_id, forecast_timestamp);
        """)
    print(f"DB initialized: {DB_PATH}")


if __name__ == "__main__":
    init_db()
