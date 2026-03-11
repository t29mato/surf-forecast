"use client";

import { useState, useRef } from "react";
import { useTranslations } from "next-intl";
import { SCORE_LEVELS } from "@/lib/colors";

export default function ScoreLegend() {
  const [visible, setVisible] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const t = useTranslations("score");

  const levels = [
    { ...SCORE_LEVELS[0], key: "excellent", range: "85〜100" },
    { ...SCORE_LEVELS[1], key: "good",      range: "65〜84"  },
    { ...SCORE_LEVELS[2], key: "fair",      range: "40〜64"  },
    { ...SCORE_LEVELS[3], key: "poor",      range: "0〜39"   },
  ];

  const factors = [
    { key: "waveHeight", weight: 30 },
    { key: "period",     weight: 25 },
    { key: "swellDir",   weight: 20 },
    { key: "wind",       weight: 20 },
    { key: "tide",       weight:  5 },
  ];

  const show = () => {
    if (timerRef.current) clearTimeout(timerRef.current);
    setVisible(true);
  };

  const hide = () => {
    timerRef.current = setTimeout(() => setVisible(false), 150);
  };

  return (
    <div className="relative inline-block">
      {/* Trigger */}
      <button
        onMouseEnter={show}
        onMouseLeave={hide}
        onFocus={show}
        onBlur={hide}
        onClick={() => setVisible((v) => !v)}
        className="flex items-center gap-1 text-xs text-gray-400 hover:text-gray-600 transition-colors px-1 py-0.5"
        aria-label={t("legendTitle")}
      >
        <span className="w-4 h-4 rounded-full border border-gray-300 hover:border-gray-500 flex items-center justify-center text-[10px] font-bold leading-none">
          ?
        </span>
        <span>{t("legendTitle")}</span>
      </button>

      {/* Popover */}
      {visible && (
        <div
          onMouseEnter={show}
          onMouseLeave={hide}
          className="absolute bottom-full left-0 mb-2 w-72 bg-white border border-gray-200 rounded-xl shadow-lg p-3 text-xs text-gray-600 z-50"
        >
          {/* Arrow */}
          <div className="absolute -bottom-1.5 left-4 w-3 h-3 bg-white border-b border-r border-gray-200 rotate-45" />

          {/* Score levels */}
          <div className="flex gap-2 mb-3">
            {levels.map(({ label, solid, text, key, range }) => (
              <div key={label} className="flex-1 text-center">
                <div
                  className="text-sm font-bold rounded-full w-7 h-7 flex items-center justify-center mx-auto mb-0.5"
                  style={{ background: solid, color: text }}
                >
                  {label}
                </div>
                <div className="font-semibold text-gray-700">{t(key as any)}</div>
                <div className="text-gray-400">{range}</div>
              </div>
            ))}
          </div>

          {/* Factors */}
          <p className="font-semibold text-gray-600 mb-1.5">{t("factorsTitle")}</p>
          <div className="space-y-1 mb-3">
            {factors.map(({ key, weight }) => (
              <div key={key} className="flex items-start gap-2">
                <div className="flex-shrink-0 w-20 text-right">
                  <span className="font-semibold text-gray-700">{t(`factors.${key}` as any)}</span>
                  <span className="text-gray-400 ml-1">{weight}%</span>
                </div>
                <div className="flex-1">
                  <div className="h-1.5 bg-gray-100 rounded-full overflow-hidden mb-0.5">
                    <div className="h-full bg-blue-300 rounded-full" style={{ width: `${weight * 3}%` }} />
                  </div>
                  <p className="text-gray-400 leading-tight">{t(`factorDesc.${key}` as any)}</p>
                </div>
              </div>
            ))}
          </div>

          <p className="text-gray-400 leading-relaxed border-t border-gray-100 pt-2">{t("note")}</p>
        </div>
      )}
    </div>
  );
}
