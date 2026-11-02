import type { Metadata } from "next";
import { Suspense } from "react";
import { WatchlistClient } from "@/components/watchlist/WatchlistClient";

export const metadata: Metadata = { title: "Watchlist" };

export default function WatchlistPage() {
  return (
    <Suspense fallback={<div className="note" style={{ marginTop: 40 }}>Loading watchlist…</div>}>
      <WatchlistClient />
    </Suspense>
  );
}
