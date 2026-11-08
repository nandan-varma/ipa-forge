import { readFileSync } from "node:fs";
import { resolve } from "node:path";

export const siteUrl = "https://ipa-forge.nandan.fyi";
// The package metadata is the version source; the docs site's npm version
// belongs to a separate, private build project.
const project = readFileSync(resolve(process.cwd(), "../pyproject.toml"), "utf8");
const version = project.match(/^version = "([^"]+)"$/m)?.[1];
if (!version) throw new Error("Cannot read package version from pyproject.toml");
export const packageVersion = version;

export function absoluteUrl(path: string): string {
  return new URL(path, siteUrl).href;
}
