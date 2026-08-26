import type { BaseLayoutProps } from "fumadocs-ui/layouts/shared";

export function baseOptions(): BaseLayoutProps {
  return {
    nav: {
      title: "ipa-forge",
    },
    githubUrl: "https://github.com/nandan-varma/ipa-forge",
    links: [
      {
        text: "Documentation",
        url: "/docs",
        active: "nested-url",
      },
      {
        text: "PyPI",
        url: "https://pypi.org/project/ipa-forge/",
        external: true,
      },
    ],
  };
}
