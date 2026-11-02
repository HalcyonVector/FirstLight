import type { Metadata } from "next";
import { ForYouClient } from "@/components/foryou/ForYouClient";

export const metadata: Metadata = { title: "For You" };

export default function ForYouPage() {
  return <ForYouClient />;
}
