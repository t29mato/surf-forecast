"use client";

import { useEffect, useRef, useState } from "react";
import "maplibre-gl/dist/maplibre-gl.css";
import type { SpotPrediction } from "@/lib/types";
import { getScoreColor } from "@/lib/colors";

interface Props {
  spots: Record<string, SpotPrediction>;
  selectedSpotId: string | null;
  onSpotSelect: (id: string) => void;
  today: string;
  displayDay: string;
  displayHour: number;
  forecastDays: string[];
  isPlaying: boolean;
  onPlayToggle: () => void;
  onDaySelect: (day: string) => void;
  onHourSelect: (hour: number) => void;
  playStep: number;
  onStepSelect: (step: number) => void;
  locale: string;
}

const HOUR_MARKS = Array.from({ length: 24 }, (_, i) => i);
const STEP_OPTIONS = [
  { step: 1,  label: "1h" },
  { step: 3,  label: "3h" },
  { step: 6,  label: "6h" },
  { step: 12, label: "12h" },
  { step: 24, label: "1d" },
];

export default function SurfMap({
  spots, selectedSpotId, onSpotSelect, today, displayDay, displayHour,
  forecastDays, isPlaying, onPlayToggle, onDaySelect, onHourSelect,
  playStep, onStepSelect, locale,
}: Props) {
  const mapContainer = useRef<HTMLDivElement>(null);
  const map = useRef<maplibregl.Map | null>(null);
  const markers = useRef<maplibregl.Marker[]>([]);
  const [mapReady, setMapReady] = useState(false);

  // Initialize map once
  useEffect(() => {
    if (!mapContainer.current) return;
    import("maplibre-gl").then((maplibregl) => {
      if (map.current) return;
      map.current = new maplibregl.Map({
        container: mapContainer.current!,
        style: {
          version: 8,
          sources: {
            osm: {
              type: "raster",
              tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
              tileSize: 256,
              attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
            },
          },
          layers: [{ id: "osm", type: "raster", source: "osm" }],
        },
        center: [136.5, 35.5],
        zoom: 5.2,
      });
      map.current.addControl(new maplibregl.NavigationControl(), "top-right");
      map.current.on("load", () => setMapReady(true));
    });

    return () => {
      markers.current.forEach((m) => m.remove());
      markers.current = [];
      map.current?.remove();
      map.current = null;
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Rebuild markers when spots / selection / displayDay / displayHour changes
  useEffect(() => {
    if (!map.current || !mapReady) return;
    import("maplibre-gl").then((maplibregl) => {
      markers.current.forEach((m) => m.remove());
      markers.current = [];

      Object.entries(spots).forEach(([spotId, spotData]) => {
        const hourTs = `${displayDay}T${String(displayHour).padStart(2, "0")}:00:00`;
        const hourly = spotData.hourly.find((h) => h.timestamp === hourTs);
        const rawScore = hourly?.score ?? spotData.daily_max[displayDay] ?? 0;
        const sc = getScoreColor(rawScore);
        const score = Math.round(rawScore * 100);
        const isSelected = spotId === selectedSpotId;

        const el = document.createElement("div");

        const badge = document.createElement("div");
        badge.style.cssText = `
          display: inline-flex; align-items: center; gap: 5px;
          background: ${isSelected ? "#f59e0b" : sc.solid}; color: ${sc.text};
          padding: ${isSelected ? "4px 10px 4px 8px" : "3px 8px 3px 7px"}; border-radius: 999px;
          font-size: ${isSelected ? "12px" : "11px"}; font-weight: 700; font-family: sans-serif;
          white-space: nowrap; cursor: pointer;
          box-shadow: 0 1px 4px rgba(0,0,0,0.35);
          border: 2px solid ${isSelected ? "#fff" : "rgba(255,255,255,0.5)"};
          transition: transform 0.12s;
          user-select: none;
        `;
        badge.innerHTML = `<span style="opacity:0.95">${spotData.spot.name}</span><span style="opacity:0.9">${score}</span>`;
        badge.addEventListener("mouseenter", () => { badge.style.transform = "scale(1.1)"; });
        badge.addEventListener("mouseleave", () => { badge.style.transform = ""; });
        badge.addEventListener("click", () => onSpotSelect(spotId));
        el.appendChild(badge);

        const marker = new maplibregl.Marker({ element: el, anchor: "center" })
          .setLngLat([spotData.spot.lon, spotData.spot.lat])
          .addTo(map.current!);

        markers.current.push(marker);
      });
    });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [spots, selectedSpotId, displayDay, displayHour, mapReady]);

  function dateLabel(d: string): string {
    const t = new Date(today);
    const tom = new Date(t);
    tom.setDate(t.getDate() + 1);
    const tomorrowStr = tom.toISOString().slice(0, 10);
    if (d === today) return locale === "ja" ? "今日" : "Today";
    if (d === tomorrowStr) return locale === "ja" ? "明日" : "Tmrw";
    const dt = new Date(`${d}T00:00:00`);
    return dt.toLocaleDateString(locale === "ja" ? "ja-JP" : "en-US", {
      month: "numeric", day: "numeric",
    });
  }

  return (
    <div ref={mapContainer} className="w-full h-full relative">
      {/* Time control bar — bottom center overlay */}
      {forecastDays.length > 0 && (
        <div
          style={{
            position: "absolute", bottom: 24, left: "50%", transform: "translateX(-50%)",
            zIndex: 10, display: "flex", flexDirection: "column", alignItems: "center", gap: 4,
            background: "rgba(15,23,42,0.88)", borderRadius: 12, padding: "8px 10px",
            boxShadow: "0 2px 12px rgba(0,0,0,0.5)", backdropFilter: "blur(4px)",
          }}
        >
          {/* Row 1: Play button + Step selector + Day tabs */}
          <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
            <button
              onClick={onPlayToggle}
              style={{
                background: isPlaying ? "#ef4444" : "#0ea5e9",
                border: "none", borderRadius: 6, color: "#fff",
                padding: "4px 10px", fontSize: 12, fontWeight: 700, cursor: "pointer",
                marginRight: 2,
              }}
            >
              {isPlaying ? "■" : "▶"}
            </button>
            {/* Step selector */}
            <div style={{ display: "flex", gap: 2, marginRight: 6 }}>
              {STEP_OPTIONS.map(({ step, label }) => (
                <button
                  key={step}
                  onClick={() => onStepSelect(step)}
                  style={{
                    background: playStep === step ? "#f59e0b" : "transparent",
                    border: playStep === step ? "none" : "1px solid rgba(255,255,255,0.2)",
                    borderRadius: 5,
                    color: playStep === step ? "#fff" : "#94a3b8",
                    padding: "3px 5px", fontSize: 10,
                    fontWeight: playStep === step ? 700 : 400,
                    cursor: "pointer", transition: "all 0.15s",
                  }}
                >
                  {label}
                </button>
              ))}
            </div>
            {forecastDays.map((d) => (
              <button
                key={d}
                onClick={() => onDaySelect(d)}
                style={{
                  background: displayDay === d ? "#0ea5e9" : "transparent",
                  border: displayDay === d ? "none" : "1px solid rgba(255,255,255,0.2)",
                  borderRadius: 6,
                  color: displayDay === d ? "#fff" : "#94a3b8",
                  padding: "4px 8px", fontSize: 11,
                  fontWeight: displayDay === d ? 700 : 400,
                  cursor: "pointer", minWidth: 38, transition: "all 0.15s",
                }}
              >
                {dateLabel(d)}
              </button>
            ))}
          </div>

          {/* Row 2: Hour selector */}
          <div style={{ display: "flex", alignItems: "center", gap: 2, width: "100%" }}>
            <span style={{ color: "#64748b", fontSize: 10, marginRight: 4, whiteSpace: "nowrap" }}>
              {locale === "ja" ? "時刻" : "Hour"}
            </span>
            {HOUR_MARKS.map((h) => {
              const isActive = displayHour === h;
              return (
                <button
                  key={h}
                  onClick={() => onHourSelect(h)}
                  style={{
                    background: isActive ? "#10b981" : "transparent",
                    border: isActive ? "none" : "1px solid rgba(255,255,255,0.1)",
                    borderRadius: 4,
                    color: isActive ? "#fff" : "#64748b",
                    padding: "3px 0", fontSize: 9, fontWeight: isActive ? 700 : 400,
                    cursor: "pointer", width: 22, transition: "all 0.15s",
                    flexShrink: 0,
                  }}
                >
                  {String(h).padStart(2, "0")}
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
