import type { Metadata } from "next";
import { Suspense } from "react";
import { AskClient } from "@/components/ask/AskClient";

export const metadata: Metadata = {
  title: "Ask the data",
  description: "Ask questions about trending GitHub repositories in plain English.",
};

export default function AskPage() {
  return (
    <Suspense fallback={<div className="note" style={{ marginTop: 40 }}>Loading…</div>}>
      <AskClient />
    </Suspense>
  );
}
