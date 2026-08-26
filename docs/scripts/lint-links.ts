import { type FileObject, printErrors, scanURLs, validateFiles } from "next-validate-link";
import { register } from "fumadocs-mdx/node";

// Resolves the `?collection=docs` bundler-loader imports fumadocs-mdx's
// generated `.source/server.ts` uses -- those only work inside Next's
// webpack/turbopack pipeline otherwise, not a plain tsx/Node run.
register();

async function checkLinks() {
  const { source } = await import("../lib/source");

  const getHeadings = ({ data }: (typeof source)["$inferPage"]): string[] =>
    data.toc.map((item) => item.url.slice(1));

  const getFiles = () => {
    const promises = source.getPages().map(
      async (page): Promise<FileObject> => ({
        path: page.absolutePath ?? page.path,
        content: await page.data.getText("raw"),
        url: page.url,
        data: page.data,
      }),
    );
    return Promise.all(promises);
  };

  const scanned = await scanURLs({
    preset: "next",
    populate: {
      "docs/[[...slug]]": source.getPages().map((page) => ({
        value: { slug: page.slugs },
        hashes: getHeadings(page),
      })),
    },
  });

  printErrors(
    await validateFiles(await getFiles(), {
      scanned,
      markdown: {
        components: {
          Card: { attributes: ["href"] },
        },
      },
      checkRelativePaths: "as-url",
    }),
    true,
  );
}

void checkLinks();
