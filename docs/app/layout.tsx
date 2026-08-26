import "./global.css";
import { RootProvider } from "fumadocs-ui/provider/next";
import type { Metadata } from "next";
import type { ReactNode } from "react";

const siteUrl = "https://ipa-forge.nandan.fyi";
const description =
  "A generic, data-driven iOS IPA patcher: extract a .ipa, apply version-aware patches from external YAML (binary byte patches, resource replace/add/remove, dylib injection), and re-sign the result for AltStore Classic sideloading.";

export const metadata: Metadata = {
  metadataBase: new URL(siteUrl),
  title: {
    default: "ipa-forge — data-driven iOS IPA patcher",
    template: "%s | ipa-forge",
  },
  description,
  keywords: [
    "ipa-forge",
    "iOS IPA patcher",
    "AltStore",
    "AltStore Classic",
    "sideloading",
    "Mach-O patching",
    "dylib injection",
    "codesign",
    "iOS tweak",
    "IPA re-signing",
  ],
  authors: [{ name: "Nandan Varma", url: "https://github.com/nandan-varma" }],
  creator: "Nandan Varma",
  applicationName: "ipa-forge",
  alternates: {
    canonical: "/",
  },
  openGraph: {
    type: "website",
    url: siteUrl,
    siteName: "ipa-forge",
    title: "ipa-forge — data-driven iOS IPA patcher",
    description,
    locale: "en_US",
  },
  twitter: {
    card: "summary_large_image",
    title: "ipa-forge — data-driven iOS IPA patcher",
    description,
  },
  robots: {
    index: true,
    follow: true,
  },
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className="flex min-h-screen flex-col">
        <RootProvider>{children}</RootProvider>
      </body>
    </html>
  );
}
