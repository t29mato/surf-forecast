"use client";

import { useState } from "react";
import { useLocale } from "next-intl";
import { useRouter } from "@/i18n/navigation";
import type { PredictionsData } from "@/lib/types";

interface Props {
  data: PredictionsData;
  today: string;
}

function scoreToColor(score: number): string {
  if (score >= 0.85) return "#3b82f6";
  if (score >= 0.65) return "#22c55e";
  if (score >= 0.40) return "#eab308";
  return "#9ca3af";
}

function scoreLabel(score: number): string {
  if (score >= 0.85) return "◎";
  if (score >= 0.65) return "○";
  if (score >= 0.40) return "△";
  return "×";
}

function isWeekend(dateStr: string): boolean {
  const d = new Date(dateStr + "T00:00:00");
  return d.getDay() === 0 || d.getDay() === 6;
}

function formatDateHeader(dateStr: string, today: string, locale: string) {
  if (dateStr === today) return { top: locale === "ja" ? "今日" : "Today", main: "", isToday: true };
  const d = new Date(dateStr + "T00:00:00");
  const dowsJa = ["日", "月", "火", "水", "木", "金", "土"];
  const dowsEn = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
  const dow = locale === "ja" ? dowsJa[d.getDay()] : dowsEn[d.getDay()];
  const main = `${d.getMonth() + 1}/${d.getDate()}`;
  return { top: dow, main, isToday: false };
}

export default function SurfForecastTable({ data, today }: Props) {
  const locale = useLocale();
  const router = useRouter();
  const isJa = locale === "ja";

  const forecastDays = Object.keys(Object.values(data.spots)[0]?.daily_max ?? {});

  // Collect all prefectures
  const prefectures = Array.from(
    new Set(Object.values(data.spots).map((s) => s.spot.prefecture))
  ).sort();

  const [selectedPref, setSelectedPref] = useState<string | null>(null);

  // Sort spots by today's score
  const sortedSpots = Object.entries(data.spots).sort(
    ([, a], [, b]) => (b.daily_max[today] ?? 0) - (a.daily_max[today] ?? 0)
  );

  const filteredSpots = selectedPref
    ? sortedSpots.filter(([, s]) => s.spot.prefecture === selectedPref)
    : sortedSpots;

  return (
    <div className="w-full">
      {/* Prefecture filter */}
      <div className="px-3 py-2 border-b border-gray-200 bg-white sticky top-0 z-30 overflow-x-auto">
        <div className="flex gap-1.5 items-center min-w-max">
          <button
            onClick={() => setSelectedPref(null)}
            className={`text-xs px-3 py-1.5 rounded-full font-medium transition-colors whitespace-nowrap ${
              selectedPref === null
                ? "bg-blue-500 text-white"
                : "bg-gray-100 text-gray-600 hover:bg-gray-200"
            }`}
          >
            {isJa ? "全国" : "All"}
          </button>
          {prefectures.map((pref) => (
            <button
              key={pref}
              onClick={() => setSelectedPref(selectedPref === pref ? null : pref)}
              className={`text-xs px-3 py-1.5 rounded-full font-medium transition-colors whitespace-nowrap ${
                selectedPref === pref
                  ? "bg-blue-500 text-white"
                  : "bg-gray-100 text-gray-600 hover:bg-gray-200"
              }`}
            >
              {pref}
            </button>
          ))}
        </div>
      </div>

      {/* Forecast table */}
      <div className="overflow-x-auto max-h-[calc(100vh-130px)]">
        <table className="w-full text-sm border-collapse min-w-[600px]">
          <thead className="sticky top-0 z-20">
            <tr className="bg-gray-50 border-b border-gray-200">
              <th className="sticky left-0 bg-gray-50 z-30 text-left px-3 py-2 font-semibold text-gray-600 min-w-[160px]">
                {isJa ? "スポット" : "Spot"}
              </th>
              {forecastDays.map((day) => {
                const { top, main, isToday } = formatDateHeader(day, today, locale);
                const weekend = isWeekend(day);
                return (
                  <th
                    key={day}
                    className={`text-center px-1.5 py-2 font-medium min-w-[64px] ${
                      isToday ? "bg-blue-50" : weekend ? "bg-red-50" : "bg-gray-50"
                    }`}
                  >
                    {isToday ? (
                      <div className="text-xs font-bold text-blue-600">{top}</div>
                    ) : (
                      <>
                        <div className={`text-xs ${weekend ? "text-red-500" : "text-gray-500"}`}>{top}</div>
                        <div className={`text-sm ${weekend ? "text-red-600 font-semibold" : "text-gray-700"}`}>{main}</div>
                      </>
                    )}
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {filteredSpots.map(([spotId, spot]) => (
              <tr
                key={spotId}
                className="border-b border-gray-100 hover:bg-blue-50 cursor-pointer transition-colors"
                onClick={() => router.push(`/spots/${spotId}`)}
              >
                <td className="sticky left-0 bg-white z-10 px-3 py-2 border-r border-gray-100">
                  <div className="font-semibold text-sm text-gray-800">{spot.spot.name}</div>
                  <div className="text-xs text-gray-400">{spot.spot.prefecture}</div>
                </td>
                {forecastDays.map((day) => {
                  const score = spot.daily_max[day] ?? 0;
                  const color = scoreToColor(score);
                  const label = scoreLabel(score);
                  const weekend = isWeekend(day);
                  const isToday = day === today;
                  return (
                    <td
                      key={day}
                      className={`text-center px-1 py-2 ${
                        isToday ? "bg-blue-50/40" : weekend ? "bg-red-50/40" : ""
                      }`}
                    >
                      <div className="font-bold text-sm leading-tight" style={{ color }}>
                        {Math.round(score * 100)}
                      </div>
                      <div className="text-xs leading-tight" style={{ color }}>
                        {label}
                      </div>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
