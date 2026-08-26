import Link from "next/link";
import type { Metadata } from "next";
import { Tab, Tabs } from "fumadocs-ui/components/tabs";

export const metadata: Metadata = {
  alternates: { canonical: "/" },
};

const features = [
  {
    title: "Data-driven patch definitions",
    body: "Binary byte patches, resource replace/add/remove, plist edits, and dylib injection — all declared in external YAML, never hardcoded to an app.",
  },
  {
    title: "Hook verification",
    body: "Every dylib hook target is checked against the app's actual Mach-O class/method tables before signing, so a renamed class fails loudly instead of silently dying at runtime.",
  },
  {
    title: "Real code signing, not reimplemented",
    body: "Apple's CodeDirectory/CMS/entitlements format is never touched directly — every signature is produced by the real codesign/security tools.",
  },
  {
    title: "Built-in reverse engineering",
    body: "forge analysis gives you class-dump, strings, symbols, security posture, and version-to-version diffing for any decrypted IPA.",
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
    <main className="mx-auto flex max-w-4xl flex-1 flex-col px-6 py-12">
      {/* eslint-disable-next-line @next/next/no-page-custom-font */}
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
      />
      <h1 className="text-4xl font-bold tracking-tight">ipa-forge</h1>
      <p className="mt-4 max-w-2xl text-lg text-fd-muted-foreground">
        A data-driven iOS IPA patcher built for AI agents. Install it with
        pip, point an agent at the docs, and it can patch, verify, and
        re-sign an <code>.ipa</code> for AltStore Classic sideloading
        unattended. Drive it yourself instead, if you'd rather.
      </p>
      <div className="mt-6 flex flex-wrap gap-3">
        <Link
          href="/docs"
          className="rounded-lg bg-fd-primary px-5 py-2.5 font-medium text-fd-primary-foreground transition-opacity hover:opacity-90"
        >
          Read the docs
        </Link>
        <a
          href="https://github.com/nandan-varma/ipa-forge"
          className="rounded-lg border px-5 py-2.5 font-medium transition-colors hover:bg-fd-accent"
        >
          View on GitHub
        </a>
        <a
          href="https://pypi.org/project/ipa-forge/"
          className="rounded-lg border px-5 py-2.5 font-medium transition-colors hover:bg-fd-accent"
        >
          Install from PyPI
        </a>
      </div>

      <Tabs items={["For AI Agents", "For Humans"]} className="mt-10">
        <Tab value="For AI Agents">
          <p className="text-sm text-fd-muted-foreground">
            Every doc page is plain Markdown:{" "}
            <a href="/llms.txt" className="underline">
              /llms.txt
            </a>{" "}
            indexes the whole site,{" "}
            <a href="/llms-full.txt" className="underline">
              /llms-full.txt
            </a>{" "}
            is all of it concatenated, and any page works with{" "}
            <code>.md</code> appended to its URL — no scraping rendered HTML.
            Give an agent a decrypted IPA and a feature to change, and it can
            run <code>forge analysis</code> / <code>forge hooks extract</code>{" "}
            to find hook targets, write the dylib, verify with{" "}
            <code>forge patch --dry-run</code>, and build the output.
          </p>
          <pre className="mt-4 overflow-x-auto rounded-lg border bg-fd-card p-4 text-sm">
            <code>{`Use https://ipa-forge.nandan.fyi/llms.txt.
Here's a decrypted App.ipa, and here's the specific
feature I want changed: <describe it>.`}</code>
          </pre>
          <p className="mt-3 text-xs text-fd-muted-foreground">
            ipa-forge doesn't decrypt IPAs or ship any app-specific
            knowledge — you supply both, and you're responsible for whether
            patching that app is something you're allowed to do.
          </p>
        </Tab>
        <Tab value="For Humans">
          <pre className="overflow-x-auto rounded-lg border bg-fd-card p-4 text-sm">
            <code>{`pip install ipa-forge

forge inspect path/to/App.ipa
forge patch --ipa <ipa> --patches <patches.yaml> \\
  --identity <id> --profile <profile> --output <out.ipa>`}</code>
          </pre>
          <p className="mt-3 text-sm text-fd-muted-foreground">
            Or skip the YAML entirely and use the local web GUI —{" "}
            <code>forge gui</code> drops an IPA in and produces an unsigned
            output for AltStore. See{" "}
            <Link href="/docs/installation" className="underline">
              Installation
            </Link>{" "}
            and{" "}
            <Link href="/docs/usage" className="underline">
              Usage
            </Link>{" "}
            for the full walkthrough.
          </p>
        </Tab>
      </Tabs>

      <div className="mt-12 grid gap-6 sm:grid-cols-2">
        {features.map((f) => (
          <div key={f.title} className="rounded-lg border p-5">
            <h2 className="font-semibold">{f.title}</h2>
            <p className="mt-2 text-sm text-fd-muted-foreground">{f.body}</p>
          </div>
        ))}
      </div>

      <div className="mt-12 rounded-lg border p-5">
        <h2 className="font-semibold">Hard constraint</h2>
        <p className="mt-2 text-sm text-fd-muted-foreground">
          Apple&apos;s code signature format (CodeDirectory, CMS, SuperBlob,
          DER entitlements) is never reimplemented. A single module is the
          only code path allowed to invoke <code>codesign</code>/
          <code>security</code> — everything else shells out through it. See{" "}
          <Link href="/docs/architecture" className="underline">
            the architecture doc
          </Link>{" "}
          for why.
        </p>
      </div>
    </main>
  );
}
