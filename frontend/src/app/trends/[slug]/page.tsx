import type { Metadata } from "next";
import { getCategoryTrend } from "@/lib/api";
import { CategoryDetailClient } from "@/components/trends/CategoryDetailClient";

export const revalidate = 300;

type Params = { params: Promise<{ slug: string }> };

export async function generateMetadata({ params }: Params): Promise<Metadata> {
  const { slug } = await params;
  try {
    const cat = await getCategoryTrend(slug, "30d");
    return {
      title: cat.category.name,
      description: `Momentum, rising repositories and weekly star growth in ${cat.category.name}.`,
    };
  } catch {
    return { title: "Category" };
  }
}

export default async function CategoryPage({ params }: Params) {
  const { slug } = await params;
  return <CategoryDetailClient slug={slug} />;
}
