import { source } from "@/lib/source";
import type { MetadataRoute } from "next";

const siteUrl = "https://ipa-forge.nandan.fyi";

export default function sitemap(): MetadataRoute.Sitemap {
  const docPages: MetadataRoute.Sitemap = source.getPages().map((page) => ({
    url: `${siteUrl}${page.url}`,
    changeFrequency: "weekly",
    priority: page.slugs.length === 0 ? 0.9 : 0.7,
  }));

  return [
    {
      url: siteUrl,
      changeFrequency: "weekly",
      priority: 1,
    },
    ...docPages,
  ];
}
