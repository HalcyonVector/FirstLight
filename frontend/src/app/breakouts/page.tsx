import type { Metadata } from "next";
import { BreakoutsClient } from "@/components/breakouts/BreakoutsClient";

export const metadata: Metadata = {
  title: "Breakout calls",
  description: "Small GitHub repositories flagged before they hit the top lists, with a public hit rate.",
};

export default function BreakoutsPage() {
  return <BreakoutsClient />;
}
