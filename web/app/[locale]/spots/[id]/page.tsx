"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell, LineChart, Line, ReferenceLine,
} from "recharts";
import type { PredictionsData, SpotPrediction, HourlyForecast } from "@/lib/types";
import { scoreBarColor, windArrow } from "@/lib/predictions";

function formatHour(ts: string) {
  return String(new Date(ts).getHours()).padStart(2, "0") + ":00";
}

function formatDay(dateStr: string, locale: string) {
  const d = new Date(dateStr + "T00:00");
  const dows = locale === "ja"
    ? ["日", "月", "火", "水", "木", "金", "土"]
    : ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
  return `${d.getMonth() + 1}/${d.getDate()}(${dows[d.getDay()]})`;
}

function ScoreBadge({ score }: { score: number }) {
  const label = score >= 0.85 ? "◎" : score >= 0.65 ? "○" : score >= 0.40 ? "△" : "×";
  const cls =
    score >= 0.85 ? "bg-blue-500 text-white" :
    score >= 0.65 ? "bg-green-500 text-white" :
    score >= 0.40 ? "bg-yellow-400 text-gray-800" :
    "bg-gray-200 text-gray-500";
  return (
    <span className={`inline-flex items-center justify-center w-8 h-8 rounded-full font-bold text-sm ${cls}`}>
      {label}
    </span>
  );
}

function ChartTooltip({ active, payload, label, locale }: any) {
  if (!active || !payload?.length) return null;
  const h = payload[0]?.payload?.raw as HourlyForecast | undefined;
  if (!h) return null;
  return (
    <div className="bg-white border border-gray-200 rounded-lg shadow-lg p-2 text-xs min-w-[140px]">
      <div className="font-bold text-gray-700 mb-1">{label}</div>
      <div className="flex items-center gap-1 mb-1">
        <ScoreBadge score={h.score} />
        <span className="text-gray-600 ml-1">{locale === "ja" ? "スコア" : "Score"} {Math.round(h.score * 100)}</span>
      </div>
      {h.wave_height_m != null && <div className="text-gray-500">{locale === "ja" ? "波高" : "Height"} {h.wave_height_m.toFixed(1)}m</div>}
      {h.wave_period_s != null && <div className="text-gray-500">{locale === "ja" ? "周期" : "Period"} {h.wave_period_s.toFixed(0)}s</div>}
      {h.wind_speed_ms != null && <div className="text-gray-500">{locale === "ja" ? "風" : "Wind"} {windArrow(h.wind_direction_deg)} {h.wind_speed_ms.toFixed(1)}m/s</div>}
    </div>
  );
}

export default function SpotPage() {
  const { id } = useParams<{ id: string }>();
  const locale = useLocale();
  const t = useTranslations("spotDetail");
  const [spot, setSpot] = useState<SpotPrediction | null>(null);
  const [selectedDay, setSelectedDay] = useState<string | null>(null);

  useEffect(() => {
    fetch("/data/predictions.json")
      .then((r) => r.json())
      .then((data: PredictionsData) => {
        const s = data.spots[id];
        if (s) {
          setSpot(s);
          const today = new Date().toISOString().slice(0, 10);
          const keys = Object.keys(s.daily_max);
          setSelectedDay(keys.includes(today) ? today : keys[0]);
        }
      });
  }, [id]);

  if (!spot) return (
    <div className="flex items-center justify-center h-full text-gray-400">
      <div className="text-center">
        <div className="text-3xl mb-2">🏄</div>
        <p>{locale === "ja" ? "読み込み中..." : "Loading..."}</p>
      </div>
    </div>
  );

  const days = Object.entries(spot.daily_max).map(([day, maxScore]) => ({ day, maxScore }));
  const today = new Date().toISOString().slice(0, 10);

  const allChartData = spot.hourly.map((h) => {
    const d = new Date(h.timestamp);
    const dayStr = h.timestamp.slice(0, 10);
    const isToday = dayStr === today;
    const dows = locale === "ja"
      ? ["日","月","火","水","木","金","土"]
      : ["Sun","Mon","Tue","Wed","Thu","Fri","Sat"];
    const dow = dows[d.getDay()];
    const todayLabel = locale === "ja" ? "今日" : "Today";
    const label = isToday
      ? `${todayLabel} ${formatHour(h.timestamp)}`
      : `${d.getMonth()+1}/${d.getDate()}(${dow}) ${formatHour(h.timestamp)}`;
    return { label, score: Math.round(h.score * 100), wave: h.wave_height_m ?? 0, wind: h.wind_speed_ms ?? 0, raw: h, dayStr, hour: d.getHours() };
  });

  const dayHourly = selectedDay ? spot.hourly.filter((h) => h.timestamp.startsWith(selectedDay)) : [];
  const dayChartData = dayHourly.map((h) => ({
    time: formatHour(h.timestamp),
    score: Math.round(h.score * 100),
    wave: h.wave_height_m ?? 0,
    raw: h,
  }));

  const bestHour = dayHourly.reduce((best, h) => (h.score > (best?.score ?? 0) ? h : best), dayHourly[0]);
  const globalBest = spot.hourly.reduce((best, h) => (h.score > (best?.score ?? 0) ? h : best), spot.hourly[0]);
  const globalBestDay = globalBest?.timestamp.slice(0, 10);

  const dayBoundaries: number[] = [];
  allChartData.forEach((d, i) => { if (i > 0 && d.hour === 0) dayBoundaries.push(i); });

  const todayLabel = locale === "ja" ? "今日" : "Today";

  return (
    <div className="h-full overflow-y-auto">
    <div className="max-w-3xl mx-auto px-4 py-4">
      <Link href="/" className="text-sm text-blue-500 hover:underline mb-4 inline-block">
        {t("back")}
      </Link>

      <div className="mb-5">
        <h1 className="text-2xl font-bold text-gray-800">{spot.spot.name}</h1>
        <p className="text-sm text-gray-400">
          {spot.spot.prefecture} ／ {t("breakType", { type: spot.spot.break_type ?? "beach" })}
        </p>
      </div>

      {/* 7-day overview chart */}
      <div className="bg-white rounded-xl border border-gray-200 p-4 mb-5">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-semibold text-gray-600">
            {locale === "ja" ? "7日間サーフスコア（1時間単位）" : "7-Day Surf Score (Hourly)"}
          </h2>
          {globalBest && (
            <div className="text-xs text-gray-400">
              {t("bestTime7d")}: {globalBestDay === today ? todayLabel : formatDay(globalBestDay, locale)}
              {" "}{formatHour(globalBest.timestamp)}
            </div>
          )}
        </div>
        <ResponsiveContainer width="100%" height={140}>
          <BarChart data={allChartData} margin={{ top: 0, right: 0, left: -28, bottom: 0 }} barCategoryGap={0}>
            <XAxis dataKey="label" tick={false} axisLine={false} tickLine={false} />
            <YAxis domain={[0, 100]} tick={{ fontSize: 9 }} width={32} />
            <Tooltip content={<ChartTooltip locale={locale} />} />
            {dayBoundaries.map((idx) => (
              <ReferenceLine key={idx} x={allChartData[idx]?.label} stroke="#e5e7eb" strokeWidth={1} />
            ))}
            <Bar dataKey="score" radius={[1, 1, 0, 0]} isAnimationActive={false}>
              {allChartData.map((entry, i) => (
                <Cell key={i} fill={scoreBarColor(entry.score / 100)} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
        <div className="flex mt-1">
          {days.map(({ day, maxScore }) => {
            const isToday = day === today;
            const label = maxScore >= 0.85 ? "◎" : maxScore >= 0.65 ? "○" : maxScore >= 0.40 ? "△" : "×";
            const countForDay = allChartData.filter(d => d.dayStr === day).length;
            const flexBasis = `${(countForDay / allChartData.length) * 100}%`;
            return (
              <button key={day} onClick={() => setSelectedDay(day)} style={{ flexBasis }}
                className={`text-center text-xs border-t-2 pt-1 transition-colors truncate ${selectedDay === day ? "border-blue-500 text-blue-700 font-semibold" : "border-transparent text-gray-400 hover:text-gray-600"}`}
              >
                {isToday ? `${todayLabel} ${label}` : `${formatDay(day, locale)} ${label}`}
              </button>
            );
          })}
        </div>
      </div>

      {selectedDay && (
        <>
          <div className="flex items-center gap-2 mb-3">
            <h2 className="text-base font-bold text-gray-700">
              {t("detailOf", { day: selectedDay === today ? todayLabel : formatDay(selectedDay, locale) })}
            </h2>
          </div>

          {bestHour && (
            <div className="bg-blue-50 border border-blue-200 rounded-xl p-4 mb-4 flex items-center gap-4">
              <ScoreBadge score={bestHour.score} />
              <div>
                <p className="font-bold text-gray-800">{t("bestTimeDay", { time: formatHour(bestHour.timestamp) })}</p>
                <p className="text-sm text-gray-500">
                  {t("waveHeight", { h: bestHour.wave_height_m?.toFixed(1) ?? "−" })}
                  ／ {t("wavePeriod", { s: bestHour.wave_period_s?.toFixed(0) ?? "−" })}
                  ／ {windArrow(bestHour.wind_direction_deg)} {bestHour.wind_speed_ms?.toFixed(1) ?? "−"}m/s
                </p>
              </div>
            </div>
          )}

          <div className="bg-white rounded-xl border border-gray-200 p-4 mb-4">
            <h2 className="text-sm font-semibold text-gray-600 mb-3">{t("scoreChart")}</h2>
            <ResponsiveContainer width="100%" height={160}>
              <BarChart data={dayChartData} margin={{ top: 0, right: 0, left: -20, bottom: 0 }}>
                <XAxis dataKey="time" tick={{ fontSize: 10 }} interval={2} />
                <YAxis domain={[0, 100]} tick={{ fontSize: 10 }} />
                <Tooltip formatter={(v) => [`${v}`, locale === "ja" ? "スコア" : "Score"]} labelFormatter={(l) => `${selectedDay} ${l}`} />
                <Bar dataKey="score" radius={[3, 3, 0, 0]}>
                  {dayChartData.map((entry, i) => (<Cell key={i} fill={scoreBarColor(entry.score / 100)} />))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>

          <div className="bg-white rounded-xl border border-gray-200 p-4 mb-4">
            <h2 className="text-sm font-semibold text-gray-600 mb-3">{t("waveChart")}</h2>
            <ResponsiveContainer width="100%" height={100}>
              <LineChart data={dayChartData} margin={{ top: 0, right: 0, left: -20, bottom: 0 }}>
                <XAxis dataKey="time" tick={{ fontSize: 10 }} interval={2} />
                <YAxis tick={{ fontSize: 10 }} />
                <Tooltip formatter={(v) => [`${v}m`, locale === "ja" ? "波高" : "Height"]} />
                <Line type="monotone" dataKey="wave" stroke="#3b82f6" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>

          <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 text-gray-500 text-xs">
                <tr>
                  <th className="text-left px-3 py-2">{t("hourlyTable.time")}</th>
                  <th className="px-3 py-2">{t("hourlyTable.score")}</th>
                  <th className="px-3 py-2">{t("hourlyTable.wave")}</th>
                  <th className="px-3 py-2">{t("hourlyTable.period")}</th>
                  <th className="px-3 py-2">{t("hourlyTable.swell")}</th>
                  <th className="px-3 py-2">{t("hourlyTable.wind")}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {dayHourly.map((h, i) => (
                  <tr key={i} className={h.score === bestHour?.score ? "bg-blue-50" : "hover:bg-gray-50"}>
                    <td className="px-3 py-2 font-mono text-gray-600">{formatHour(h.timestamp)}</td>
                    <td className="px-3 py-2 text-center"><ScoreBadge score={h.score} /></td>
                    <td className="px-3 py-2 text-center text-gray-700">{h.wave_height_m?.toFixed(1) ?? "−"}m</td>
                    <td className="px-3 py-2 text-center text-gray-700">{h.wave_period_s?.toFixed(0) ?? "−"}s</td>
                    <td className="px-3 py-2 text-center text-gray-700">{h.swell_height_m?.toFixed(1) ?? "−"}m</td>
                    <td className="px-3 py-2 text-center text-gray-600">{windArrow(h.wind_direction_deg)} {h.wind_speed_ms?.toFixed(1) ?? "−"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
    </div>
  );
}
