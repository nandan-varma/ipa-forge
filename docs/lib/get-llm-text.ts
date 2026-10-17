import { absoluteUrl, packageVersion } from "@/lib/project";
import { source } from "@/lib/source";

export async function getLLMText(page: (typeof source)["$inferPage"]) {
  const processed = await page.data.getText("processed");

  return `# ${page.data.title}\n\nSource: ${absoluteUrl(page.url)}\nMarkdown: ${absoluteUrl(`${page.url}.md`)}\nPackage version: ${packageVersion}; docs follow main and may include unreleased changes.\n\n${processed}`;
}
