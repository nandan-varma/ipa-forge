import type { MetadataRoute } from "next";

const siteUrl = "https://ipa-forge.nandan.fyi";

export default function robots(): MetadataRoute.Robots {
  return {
    rules: {
      userAgent: "*",
      allow: "/",
    },
    sitemap: `${siteUrl}/sitemap.xml`,
  };
}
