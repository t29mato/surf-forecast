import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Surf Forecast Japan",
  description: "ML-powered hourly surf score predictions for Japan",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ja">
      <body className="h-screen overflow-hidden bg-gray-50 text-gray-900">
        {children}
      </body>
    </html>
  );
}
