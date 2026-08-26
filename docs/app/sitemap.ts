import { source } from "@/lib/source";
import type { MetadataRoute } from "next";

const siteUrl = "https://ipa-forge.nandan.fyi";

export default function sitemap(): MetadataRoute.Sitemap {
  const docPages: MetadataRoute.Sitemap = source.getPages().map((page) => ({
    url: `${siteUrl}/docs/${page.slugs.join("/")}`,
    lastModified: new Date(),
    changeFrequency: "weekly",
    priority: page.slugs.length === 0 ? 0.9 : 0.7,
  }));

  return [
    {
      url: siteUrl,
      lastModified: new Date(),
      changeFrequency: "weekly",
      priority: 1,
    },
    ...docPages,
  ];
}
