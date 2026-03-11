import type { PredictionsData, SpotPrediction } from "./types";
import { getScoreColor } from "./colors";

export async function getPredictions(): Promise<PredictionsData> {
  const res = await fetch("/data/predictions.json", { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to load predictions");
  return res.json();
}

export function scoreColor(score: number): string {
  if (score >= 0.85) return "bg-blue-500 text-white";
  if (score >= 0.65) return "bg-green-500 text-white";
  if (score >= 0.40) return "bg-yellow-400 text-gray-800";
  return "bg-gray-300 text-gray-600";
}

export function scoreColorBorder(score: number): string {
  if (score >= 0.85) return "border-blue-500";
  if (score >= 0.65) return "border-green-500";
  if (score >= 0.40) return "border-yellow-400";
  return "border-gray-300";
}

export function labelColor(label: string): string {
  switch (label) {
    case "◎": return "text-blue-600 font-bold";
    case "○": return "text-green-600 font-bold";
    case "△": return "text-yellow-600";
    default:   return "text-gray-400";
  }
}

export function scoreBarColor(score: number): string {
  return getScoreColor(score).solid;
}

export function windArrow(deg: number | null): string {
  if (deg === null) return "−";
  const dirs = ["N","NE","E","SE","S","SW","W","NW"];
  return dirs[Math.round(deg / 45) % 8];
}

export function getTodayRanking(data: PredictionsData): Array<{ spotId: string; spot: SpotPrediction; todayMax: number }> {
  const today = new Date().toISOString().slice(0, 10);
  return Object.entries(data.spots)
    .map(([spotId, spot]) => {
      const todayMax = spot.daily_max[today] ?? 0;
      return { spotId, spot, todayMax };
    })
    .sort((a, b) => b.todayMax - a.todayMax);
}
