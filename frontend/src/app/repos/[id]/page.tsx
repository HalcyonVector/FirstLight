import type { Metadata } from "next";
import { getRepository } from "@/lib/api";
import { RepoDetailClient } from "@/components/repo/RepoDetailClient";

type Params = { params: Promise<{ id: string }> };

export async function generateMetadata({ params }: Params): Promise<Metadata> {
  const { id } = await params;
  try {
    const repo = await getRepository(Number(id));
    return {
      title: repo.full_name,
      description: repo.description ?? `Momentum, star growth and AI analysis for ${repo.full_name}.`,
    };
  } catch {
    return { title: "Repository" };
  }
}

export default async function RepoPage({ params }: Params) {
  const { id } = await params;
  return <RepoDetailClient id={Number(id)} />;
}
