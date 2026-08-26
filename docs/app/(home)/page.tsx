import Link from "next/link";
import type { Metadata } from "next";
import { Tab, Tabs } from "fumadocs-ui/components/tabs";

export const metadata: Metadata = {
  alternates: { canonical: "/" },
};

const features = [
  {
    title: "Data-driven patches",
    body: "Every patch is declared in external YAML — never hardcoded to an app.",
  },
  {
    title: "Hook verification",
    body: "Every hook is checked against the real binary before signing.",
  },
  {
    title: "Real code signing",
    body: "Signatures come from Apple's own codesign — never reimplemented.",
  },
  {
    title: "Built-in reverse engineering",
    body: "Class-dump, strings, symbols, and version diffing via forge analysis.",
  },
];

const jsonLd = {
  "@context": "https://schema.org",
  "@type": "SoftwareSourceCode",
  name: "ipa-forge",
  description:
    "A data-driven iOS IPA patcher built for AI agents: pip install it, point an agent at the docs, and it can patch, verify, and re-sign an IPA for AltStore Classic sideloading.",
  codeRepository: "https://github.com/nandan-varma/ipa-forge",
  programmingLanguage: "Python",
  license: "https://www.gnu.org/licenses/gpl-3.0.html",
  author: {
    "@type": "Person",
    name: "Nandan Varma",
    url: "https://github.com/nandan-varma",
  },
};

export default function HomePage() {
  return (
    <main className="mx-auto flex w-full max-w-4xl flex-1 flex-col px-4 py-8 sm:px-6 sm:py-12">
      {/* eslint-disable-next-line @next/next/no-page-custom-font */}
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
      />
      <h1 className="text-3xl font-bold tracking-tight sm:text-4xl">ipa-forge</h1>
      <p className="mt-3 max-w-xl text-base text-fd-muted-foreground sm:text-lg">
        The iOS IPA patcher built for AI agents. Install with pip, point an
        agent at the docs, and it patches, verifies, and signs — unattended.
      </p>
      <div className="mt-6 grid grid-cols-2 gap-2 sm:flex sm:flex-wrap sm:gap-3">
        <Link
          href="/docs"
          className="col-span-2 rounded-lg bg-fd-primary px-5 py-2.5 text-center font-medium text-fd-primary-foreground transition-opacity hover:opacity-90 sm:col-span-1"
        >
          Read the docs
        </Link>
        <a
          href="https://github.com/nandan-varma/ipa-forge"
          className="rounded-lg border px-5 py-2.5 text-center font-medium transition-colors hover:bg-fd-accent"
        >
          GitHub
        </a>
        <a
          href="https://pypi.org/project/ipa-forge/"
          className="rounded-lg border px-5 py-2.5 text-center font-medium transition-colors hover:bg-fd-accent"
        >
          PyPI
        </a>
      </div>

      <Tabs items={["For AI Agents", "For Humans"]} className="mt-8">
        <Tab value="For AI Agents">
          <p className="text-sm text-fd-muted-foreground">
            Give an agent a decrypted IPA and this prompt:
          </p>
          <pre className="mt-3 overflow-x-auto rounded-lg border bg-fd-card p-3 text-xs sm:p-4 sm:text-sm">
            <code>{`Use https://ipa-forge.nandan.fyi/llms.txt.
Here's a decrypted App.ipa, and here's the specific
feature I want changed: <describe it>.`}</code>
          </pre>
          <p className="mt-3 text-xs text-fd-muted-foreground">
            Every page is plain Markdown (append <code>.md</code>, or see{" "}
            <a href="/llms.txt" className="underline">
              /llms.txt
            </a>
            ). ipa-forge supplies neither the decryption nor the app-specific
            knowledge — that part's on you.
          </p>
        </Tab>
        <Tab value="For Humans">
          <pre className="overflow-x-auto rounded-lg border bg-fd-card p-3 text-xs sm:p-4 sm:text-sm">
            <code>{`pip install ipa-forge

forge inspect path/to/App.ipa
forge patch --ipa <ipa> --patches <patches.yaml> \\
  --identity <id> --profile <profile> --output <out.ipa>`}</code>
          </pre>
          <p className="mt-3 text-xs text-fd-muted-foreground">
            Prefer a GUI? <code>forge gui</code> drops an IPA in, no YAML
            required. See{" "}
            <Link href="/docs/installation" className="underline">
              Installation
            </Link>{" "}
            for the full walkthrough.
          </p>
        </Tab>
      </Tabs>

      <div className="mt-10 grid gap-4 sm:grid-cols-2">
        {features.map((f) => (
          <div key={f.title} className="rounded-lg border p-4">
            <h2 className="text-sm font-semibold">{f.title}</h2>
            <p className="mt-1 text-sm text-fd-muted-foreground">{f.body}</p>
          </div>
        ))}
      </div>
    </main>
  );
}
