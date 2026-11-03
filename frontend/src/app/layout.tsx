import type { Metadata } from "next";
import { Fraunces, Inter, JetBrains_Mono } from "next/font/google";
import "./globals.css";
import { Providers } from "@/components/layout/Providers";
import { AppShell } from "@/components/layout/AppShell";

const fraunces = Fraunces({
  variable: "--font-fraunces",
  subsets: ["latin"],
  weight: ["400", "500", "600", "900"],
  display: "swap",
});

const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  display: "swap",
});

const jetbrains = JetBrains_Mono({
  variable: "--font-mono",
  subsets: ["latin"],
  weight: ["400", "500", "700"],
  display: "swap",
});

// Render every page dynamically from the live API rather than a build-time cache,
// so momentum/leaderboards reflect the latest 6-hourly data (no stale ISR snapshot).
export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  // Absolute base for share-image URLs. Vercel provides the production domain
  // when NEXT_PUBLIC_SITE_URL isn't set.
  metadataBase: new URL(
    process.env.NEXT_PUBLIC_SITE_URL ??
      (process.env.VERCEL_PROJECT_PRODUCTION_URL
        ? `https://${process.env.VERCEL_PROJECT_PRODUCTION_URL}`
        : "http://localhost:2326")
  ),
  title: {
    default: "FirstLight",
    template: "%s · FirstLight",
  },
  description:
    "See open source early. FirstLight tracks trending GitHub repositories, explains why they are growing, and calls breakouts before they hit the top lists.",
  keywords: ["github", "trending", "open source", "ai", "developer tools", "repositories"],
  openGraph: { type: "website", siteName: "FirstLight" },
  alternates: { types: { "application/rss+xml": "/rss.xml" } },
};

// Runs before paint to apply the saved theme (or the OS light/dark setting on a
// first visit) and avoid a flash of the default.
const themeScript = `(function(){try{var t=localStorage.getItem('gti:theme');if(t!=='dusk'&&t!=='paper'){t=window.matchMedia('(prefers-color-scheme: light)').matches?'paper':'dusk';}document.documentElement.setAttribute('data-theme',t);}catch(e){}})();`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" data-theme="dusk" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body
        className={`${fraunces.variable} ${inter.variable} ${jetbrains.variable}`}
        suppressHydrationWarning
      >
        <div className="aurora" aria-hidden="true">
          <b />
          <b />
          <b />
        </div>
        <div className="grain" aria-hidden="true" />
        <Providers>
          <AppShell>{children}</AppShell>
        </Providers>
      </body>
    </html>
  );
}
