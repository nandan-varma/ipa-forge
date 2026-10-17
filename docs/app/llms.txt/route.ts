import { source } from "@/lib/source";
import { absoluteUrl, packageVersion } from "@/lib/project";

export const revalidate = false;

export function GET() {
  const pages = source.getPages().map((page) =>
    `- [${page.data.title}](${absoluteUrl(`${page.url}.md`)}): ${page.data.description ?? ""}`,
  );
  return new Response([
    "# ipa-forge",
    "",
    `Package version: ${packageVersion}. These docs follow main and may describe unreleased changes; check forge --version and command --help.`,
    "",
    "A Python CLI for inspecting and patching user-supplied decrypted iOS IPAs using external YAML definitions. No third-party patch sets or decryption are supplied.",
    "",
    "## Start here",
    `- Installation and platform requirements: ${absoluteUrl("/docs/installation.md")}`,
    `- CLI output and usage: ${absoluteUrl("/docs/usage.md")}`,
    `- New app workflow: ${absoluteUrl("/docs/adding-an-app.md")}`,
    "",
    "Use task-specific Markdown pages below rather than loading all documentation. Signing and Objective-C hook/class analysis need macOS tools. Patching needs a definition and its assets; GUI discovery requires IPA_FORGE_PATCHES_DIR. Run lint, then dry-run before applying changes; static hook checks do not establish on-device behavior.",
    "",
    "## Documentation",
    ...pages,
    "",
    `Full documentation (larger context): ${absoluteUrl("/llms-full.txt")}`,
    "",
  ].join("\n"), { headers: { "Content-Type": "text/plain; charset=utf-8" } });
}
