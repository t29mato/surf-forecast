"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import dynamic from "next/dynamic";
import { useLocale, useTranslations } from "next-intl";
import { useRouter, usePathname, Link } from "@/i18n/navigation";
import type { PredictionsData, SpotPrediction } from "@/lib/types";
import { scoreColor, windArrow } from "@/lib/predictions";
import ScoreLegend from "@/components/ScoreLegend";
import { getScoreColor, SCORE_LEVELS } from "@/lib/colors";

const SurfMap = dynamic(() => import("@/components/SurfMap"), { ssr: false });
import SurfForecastTable from "@/components/SurfForecastTable";

type PageView = "map" | "table";

function scoreToColor(s: number) {
  return getScoreColor(s).solid;
}

export default function HomePage() {
  const t = useTranslations("home");
  const locale = useLocale();
  const router = useRouter();
  const pathname = usePathname();

  const [data, setData] = useState<PredictionsData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pageView, setPageView] = useState<PageView>("map");
  const [selectedSpotId, setSelectedSpotId] = useState<string | null>(null);
  const [showPanel, setShowPanel] = useState(true);
  const [displayDay, setDisplayDay] = useState<string>("");
  const [displayHour, setDisplayHour] = useState<number>(() => new Date().getHours());
  const [isPlaying, setIsPlaying] = useState(false);
  const [playStep, setPlayStep] = useState<number>(1);

  const playRef = useRef(false);
  const playStepRef = useRef(1);
  const timelineRef = useRef<{ day: string; hour: number }[]>([]);
  const timelineIdxRef = useRef(0);

  const today = new Date().toISOString().slice(0, 10);

  useEffect(() => {
    fetch("/data/predictions.json")
      .then((r) => r.json())
      .then((d: PredictionsData) => {
        setData(d);
        setDisplayDay(today);
      })
      .catch(() => setError("Failed to load forecast data"));
  }, []);

  const forecastDays = data
    ? Object.keys(Object.values(data.spots)[0]?.daily_max ?? {})
    : [];

  // Build flat timeline: every hour across all forecast days
  const timeline = forecastDays.flatMap((day) =>
    Array.from({ length: 24 }, (_, h) => ({ day, hour: h }))
  );

  // Build stepped timeline based on playStep
  const buildSteppedTimeline = (step: number) =>
    timeline.filter((_, i) => i % step === 0);

  const startPlay = useCallback(() => {
    if (timeline.length === 0) return;
    setIsPlaying(true);
    playRef.current = true;
    timelineRef.current = buildSteppedTimeline(playStepRef.current);
    // sync current position
    const cur = timelineRef.current.findIndex(
      (t) => t.day === displayDay && t.hour === displayHour
    );
    timelineIdxRef.current = cur >= 0 ? cur : 0;
    const tick = () => {
      if (!playRef.current) return;
      timelineIdxRef.current = (timelineIdxRef.current + 1) % timelineRef.current.length;
      const { day, hour } = timelineRef.current[timelineIdxRef.current];
      setDisplayDay(day);
      setDisplayHour(hour);
      setTimeout(tick, 400);
    };
    setTimeout(tick, 400);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [timeline.length, displayDay, displayHour]);

  const handleStepSelect = useCallback((step: number) => {
    setPlayStep(step);
    playStepRef.current = step;
  }, []);

  const stopPlay = useCallback(() => {
    setIsPlaying(false);
    playRef.current = false;
  }, []);

  const handlePlayToggle = useCallback(() => {
    if (isPlaying) stopPlay(); else startPlay();
  }, [isPlaying, startPlay, stopPlay]);

  const handleDaySelect = useCallback((day: string) => {
    stopPlay();
    setDisplayDay(day);
    const idx = timeline.findIndex((t) => t.day === day && t.hour === displayHour);
    if (idx >= 0) timelineIdxRef.current = idx;
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stopPlay, displayHour]);

  const handleHourSelect = useCallback((hour: number) => {
    stopPlay();
    setDisplayHour(hour);
    const idx = timeline.findIndex((t) => t.day === displayDay && t.hour === hour);
    if (idx >= 0) timelineIdxRef.current = idx;
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stopPlay, displayDay]);

  const handleSpotSelect = useCallback((id: string) => {
    setSelectedSpotId((prev) => (prev === id ? null : id));
    setShowPanel(true);
  }, []);

  const loading = !data || !displayDay;

  const ranking = data
    ? Object.entries(data.spots)
        .map(([spotId, spot]) => {
          const hourTs = `${displayDay}T${String(displayHour).padStart(2, "0")}:00:00`;
          const hourly = spot.hourly.find((h) => h.timestamp === hourTs);
          const displayScore = hourly?.score ?? spot.daily_max[displayDay] ?? 0;
          const dayHourly = spot.hourly.filter((h) => h.timestamp.startsWith(displayDay));
          return { spotId, spot, displayScore, dayHourly };
        })
        .sort((a, b) => b.displayScore - a.displayScore)
    : [];

  const generatedAt = data
    ? new Date(data.generated_at).toLocaleString(
        locale === "ja" ? "ja-JP" : "en-US",
        { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" }
      )
    : "";

  const selectedSpot = selectedSpotId && data ? data.spots[selectedSpotId] : null;

  const dows =
    locale === "ja"
      ? ["日", "月", "火", "水", "木", "金", "土"]
      : ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

  function dayLabel(day: string) {
    if (day === today) return locale === "ja" ? "今日" : "Today";
    const d = new Date(day + "T00:00");
    return `${d.getMonth() + 1}/${d.getDate()}(${dows[d.getDay()]})`;
  }

  if (error) return <p className="text-red-500 p-4">{error}</p>;

  return (
    <div className="h-screen flex flex-col">
      {/* ── Header ── */}
      <header className="bg-white border-b border-gray-200 px-4 py-3 flex items-center justify-between flex-shrink-0 z-20">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 bg-blue-500 rounded-lg flex items-center justify-center text-white text-base">
            🏄
          </div>
          <div>
            <h1 className="text-base font-bold leading-tight">{t("title")}</h1>
            <p className="text-xs text-gray-400 leading-tight">{t("subtitle")}</p>
          </div>
        </div>
        <div className="flex items-center gap-3 text-sm text-gray-500">
          {/* Map / Table toggle */}
          <div className="flex bg-gray-100 rounded-lg p-0.5">
            <button
              onClick={() => setPageView("map")}
              className={`px-3 py-1.5 rounded-md text-sm font-medium transition-all ${
                pageView === "map"
                  ? "bg-white shadow-sm text-gray-900"
                  : "text-gray-500 hover:text-gray-700"
              }`}
            >
              {t("mapButton")}
            </button>
            <button
              onClick={() => setPageView("table")}
              className={`px-3 py-1.5 rounded-md text-sm font-medium transition-all ${
                pageView === "table"
                  ? "bg-blue-100 shadow-sm text-blue-800"
                  : "text-gray-500 hover:text-gray-700"
              }`}
            >
              {t("listButton")}
            </button>
          </div>
          {/* Score legend dots */}
          <div className="hidden sm:flex items-center gap-2">
            {SCORE_LEVELS.map(({ solid, label, range }) => (
              <span key={label} className="flex items-center gap-1">
                <span className="w-3 h-3 rounded-full inline-block" style={{ background: solid }} />
                <span className="hidden md:inline text-xs text-gray-500">{range}</span>
              </span>
            ))}
          </div>
          {/* Language toggle */}
          <button
            onClick={() => router.replace(pathname, { locale: locale === "ja" ? "en" : "ja" })}
            className="px-3 py-1.5 rounded border border-gray-300 hover:bg-gray-100 text-sm font-medium"
          >
            {locale === "ja" ? "EN" : "JA"}
          </button>
        </div>
      </header>

      {/* ── Main content ── */}
      {pageView === "map" ? (
        <div className="flex-1 flex relative overflow-hidden">
          {/* Map */}
          <div className="flex-1 relative">
            {loading ? (
              <div className="flex items-center justify-center h-full text-gray-400">
                <div className="text-center">
                  <div className="text-3xl mb-2">🏄</div>
                  <p>{locale === "ja" ? "読み込み中..." : "Loading..."}</p>
                </div>
              </div>
            ) : (
              <SurfMap
                spots={data!.spots}
                selectedSpotId={selectedSpotId}
                onSpotSelect={handleSpotSelect}
                today={today}
                displayDay={displayDay}
                displayHour={displayHour}
                forecastDays={forecastDays}
                isPlaying={isPlaying}
                onPlayToggle={handlePlayToggle}
                onDaySelect={handleDaySelect}
                onHourSelect={handleHourSelect}
                playStep={playStep}
                onStepSelect={handleStepSelect}
                locale={locale}
              />
            )}
          </div>

          {/* Side panel */}
          <div
            className={`absolute right-0 top-0 bottom-0 w-80 bg-gray-50 border-l border-gray-200 overflow-y-auto transition-transform duration-300 z-10 ${
              showPanel ? "translate-x-0" : "translate-x-full"
            } sm:relative sm:translate-x-0`}
          >
            <div className="p-3">
              {selectedSpot ? (
                /* Spot detail */
                <div>
                  <div className="flex items-start justify-between mb-3">
                    <div>
                      <h2 className="font-bold text-gray-800 text-lg">{selectedSpot.spot.name}</h2>
                      <p className="text-xs text-gray-400">
                        {selectedSpot.spot.prefecture} / {selectedSpot.spot.break_type}
                      </p>
                    </div>
                    <button
                      onClick={() => setSelectedSpotId(null)}
                      className="text-gray-400 hover:text-gray-600 text-xl leading-none"
                    >
                      ×
                    </button>
                  </div>
                  <div className="space-y-1 mb-4">
                    {Object.entries(selectedSpot.daily_max).map(([day, score]) => {
                      const isActive = day === displayDay;
                      return (
                        <button
                          key={day}
                          onClick={() => handleDaySelect(day)}
                          className={`w-full flex items-center gap-2 rounded-lg px-2 py-1 transition-colors text-left ${
                            isActive ? "bg-blue-50 ring-1 ring-blue-300" : "hover:bg-gray-50"
                          }`}
                        >
                          <span className="text-xs text-gray-500 w-24 flex-shrink-0">{dayLabel(day)}</span>
                          <div className="flex-1 bg-gray-100 rounded-full h-2 overflow-hidden">
                            <div
                              className="h-full rounded-full transition-all"
                              style={{ width: `${score * 100}%`, backgroundColor: scoreToColor(score) }}
                            />
                          </div>
                          <span
                            className="text-xs font-bold tabular-nums w-6 text-right"
                            style={{ color: scoreToColor(score) }}
                          >
                            {Math.round(score * 100)}
                          </span>
                        </button>
                      );
                    })}
                  </div>
                  <Link
                    href={`/spots/${selectedSpotId}`}
                    className="block w-full text-center bg-blue-500 hover:bg-blue-600 text-white text-sm font-medium py-2 rounded-lg transition-colors"
                  >
                    {locale === "ja" ? "時間別予報を見る →" : "View Hourly Forecast →"}
                  </Link>
                </div>
              ) : (
                /* Ranking list */
                <>
                  <h2 className="text-base font-semibold text-gray-600 mb-3">{t("rankingTitle")}</h2>
                  {data && (
                    <p className="text-xs text-gray-400 mb-3">{t("updatedAt", { time: generatedAt })}</p>
                  )}
                  <div className="space-y-2">
                    {ranking.map(({ spotId, spot, displayScore }, i) => {
                      const label = displayScore >= 0.85 ? "◎" : displayScore >= 0.65 ? "○" : displayScore >= 0.40 ? "△" : "×";
                      return (
                        <button
                          key={spotId}
                          onClick={() => handleSpotSelect(spotId)}
                          className="w-full text-left p-3 rounded-lg border border-gray-200 bg-white hover:border-gray-300 hover:shadow-sm transition-all"
                        >
                          <div className="flex items-center gap-3">
                            <span className="text-base font-bold text-gray-300 w-6 text-center">{i + 1}</span>
                            <div
                              className="w-9 h-9 rounded-full flex items-center justify-center text-base font-bold flex-shrink-0"
                              style={{
                                backgroundColor: scoreToColor(displayScore),
                                color: "white",
                              }}
                            >
                              {label}
                            </div>
                            <div className="flex-1 min-w-0">
                              <div className="font-semibold text-gray-800 text-sm truncate">{spot.spot.name}</div>
                              <div className="text-xs text-gray-400">{spot.spot.prefecture}</div>
                            </div>
                            <span
                              className="text-lg font-bold tabular-nums"
                              style={{ color: scoreToColor(displayScore) }}
                            >
                              {Math.round(displayScore * 100)}
                            </span>
                          </div>
                        </button>
                      );
                    })}
                  </div>
                  <div className="mt-3">
                    <ScoreLegend />
                  </div>
                </>
              )}
            </div>
          </div>

          {/* Mobile toggle */}
          <button
            onClick={() => setShowPanel(!showPanel)}
            className="sm:hidden absolute bottom-4 right-4 z-20 bg-white rounded-full p-3 shadow-lg border border-gray-200 text-gray-600"
          >
            {showPanel ? "›" : "‹"}
          </button>
        </div>
      ) : (
        /* ── Table / List view ── */
        <div className="flex-1 overflow-auto bg-white">
          {loading ? (
            <div className="flex items-center justify-center h-full text-gray-400">
              <p>{locale === "ja" ? "読み込み中..." : "Loading..."}</p>
            </div>
          ) : (
            <SurfForecastTable data={data!} today={today} />
          )}
        </div>
      )}
    </div>
  );
}
