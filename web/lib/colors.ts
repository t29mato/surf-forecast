/** Centralised surf score colour system */

export interface ScoreColor {
  solid: string;
  text:  string;
}

const LEVELS: [number, ScoreColor][] = [
  [0.85, { solid: "#0ea5e9", text: "#ffffff" }], // ◎ 空青
  [0.65, { solid: "#10b981", text: "#ffffff" }], // ○ エメラルド
  [0.40, { solid: "#f59e0b", text: "#ffffff" }], // △ アンバー
  [0.00, { solid: "#94a3b8", text: "#ffffff" }], // × スレート
];

export function getScoreColor(score: number): ScoreColor {
  for (const [threshold, color] of LEVELS) {
    if (score >= threshold) return color;
  }
  return LEVELS[LEVELS.length - 1][1];
}

export const SCORE_LEVELS = [
  { label: "◎", range: "85+", ...LEVELS[0][1] },
  { label: "○", range: "65+", ...LEVELS[1][1] },
  { label: "△", range: "40+", ...LEVELS[2][1] },
  { label: "×", range: "−",  ...LEVELS[3][1] },
];
