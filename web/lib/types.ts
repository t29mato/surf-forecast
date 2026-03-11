export type ScoreLabel = "◎" | "○" | "△" | "×";

export interface HourlyForecast {
  timestamp: string;
  score: number;
  label: ScoreLabel;
  wave_height_m: number | null;
  wave_period_s: number | null;
  swell_height_m: number | null;
  wind_speed_ms: number | null;
  wind_direction_deg: number | null;
}

export interface SpotInfo {
  id: string;
  name: string;
  prefecture: string;
  region: string;
  lat: number;
  lon: number;
  break_type: string | null;
}

export interface SpotPrediction {
  spot: SpotInfo;
  hourly: HourlyForecast[];
  daily_max: Record<string, number>;
  best_time_7d: string;
}

export interface PredictionsData {
  generated_at: string;
  model_version: string;
  forecast_days: number;
  spots: Record<string, SpotPrediction>;
}
