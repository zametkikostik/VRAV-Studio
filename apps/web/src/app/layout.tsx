import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "VRAV Studio",
  description: "AI-assisted video production platform",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ru">
      <body>{children}</body>
    </html>
  );
}
