import Link from "next/link";
import type { Metadata } from "next";

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
    "A generic, data-driven iOS IPA patcher: extract a .ipa, apply version-aware patches from external YAML, and re-sign the result for AltStore Classic sideloading.",
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
    <main className="mx-auto flex max-w-4xl flex-1 flex-col px-6 py-16">
      {/* eslint-disable-next-line @next/next/no-page-custom-font */}
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
      />
      <h1 className="text-4xl font-bold tracking-tight">ipa-forge</h1>
      <p className="mt-4 max-w-2xl text-lg text-fd-muted-foreground">
        A generic, data-driven iOS IPA patcher framework. Extract a
        user-supplied <code>.ipa</code>, apply version-aware patches from
        external YAML — binary byte patches, resource replace/add/remove,
        dylib injection — and re-sign the result into a standard-structure{" "}
        <code>.ipa</code> that AltStore Classic can install and refresh on a
        real iPhone.
      </p>
      <div className="mt-8 flex flex-wrap gap-3">
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

      <pre className="mt-10 overflow-x-auto rounded-lg border bg-fd-card p-4 text-sm">
        <code>{`pip install ipa-forge

forge inspect path/to/App.ipa
forge patch --ipa <ipa> --patches <patches.yaml> \\
  --identity <id> --profile <profile> --output <out.ipa>`}</code>
      </pre>

      <div className="mt-16 grid gap-6 sm:grid-cols-2">
        {features.map((f) => (
          <div key={f.title} className="rounded-lg border p-5">
            <h2 className="font-semibold">{f.title}</h2>
            <p className="mt-2 text-sm text-fd-muted-foreground">{f.body}</p>
          </div>
        ))}
      </div>

      <div className="mt-16 rounded-lg border p-5">
        <h2 className="font-semibold">Built for AI agents, not just people</h2>
        <p className="mt-2 text-sm text-fd-muted-foreground">
          Every doc page is available as plain Markdown —{" "}
          <a href="/llms.txt" className="underline">
            /llms.txt
          </a>{" "}
          indexes the whole site,{" "}
          <a href="/llms-full.txt" className="underline">
            /llms-full.txt
          </a>{" "}
          is all of it concatenated, and any page works with <code>.md</code>{" "}
          appended to its URL. A tool-using agent can read the CLI/GUI
          reference, the patch-definition format, and the hook-verification
          loop directly — no scraping rendered HTML required.
        </p>
        <p className="mt-3 text-sm text-fd-muted-foreground">
          Give it a decrypted IPA and a specific feature to change, and it
          can run <code>forge analysis</code> / <code>forge hooks extract</code>{" "}
          to find the right hook targets, write the dylib, verify with{" "}
          <code>forge patch --dry-run</code>, and build the output —
          unattended:
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
      </div>

      <div className="mt-16 rounded-lg border p-5">
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
