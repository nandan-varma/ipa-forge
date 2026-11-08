# Onboarding and discovery audit — 2026-10-17

Baseline: `59743bf` (after the 0.2.0 release). Changes are local on
`improve/onboarding-and-discovery`; nothing in this audit was deployed.
This records verified observations and distinguishes recommendations from
facts. It does not claim exhaustive proof of every behavior or search ranking.

## Review of the original recommendations

| Claim / recommendation | Evidence at baseline | Resolution |
| --- | --- | --- |
| Add a prerequisite diagnostic | No doctor command in `ipa_forge/cli/main.py`; archive operations call external zip/unzip, ObjC analysis calls lipo/otool, signing backend calls codesign/security | Added opt-in doctor checks, fixes, and JSON. Checks tool presence, not credential validity or on-device behavior. |
| Simplify the first demo | Installation guide required three manual fixture/asset downloads and multiple commands | Added an offline bundled demo using the actual synthetic IPA. Lints, dry-runs, applies unsigned, verifies the manifest, cleans up. |
| Explain patch-set discovery | `patches.py` scans a package-relative root or `IPA_FORGE_PATCHES_DIR`; the wheel ships no third-party patches | **Correction:** the usage guide already explained this well. Surfaced it in README, installation guide, homepage, and GUI before upload. |
| Add consistent JSON output | Core commands lacked JSON flags; hooks verify/find/audit and analysis classdump/il2cpp already had JSON | Added a versioned envelope for core commands. Existing hook/analysis formats remain unchanged. Remaining text-only commands are explicitly documented; no claim of universal JSON support. |
| Publish a definition schema | Pydantic models existed; no exported editor schema or schema command | Added generated JSON Schema, editor instructions, export command, artifact drift check, and static-route smoke check. Runtime semantic checks still require lint/dry-run. |
| Make examples release-aware | Installation/README fixtures pointed at changing main; docs and Python package deploy independently | Pinned those fixture links to v0.2.0. Agent documents identify package version and warn that main may include unreleased commands. New commands are labelled as post-0.2.0 source features. |
| Share agent instructions | Detailed guidance existed only in CLAUDE.md | Moved shared guidance to AGENTS.md; CLAUDE.md points there. Corrected stale platform guidance during the move. |
| Strengthen docs CI | Reusable checks only ran Python lint/types/tests; a link checker already existed but was not in CI | Added production docs build, link validation, and HTML/Markdown/schema/robots/sitemap checks. |
| Improve search landing pages | Thirteen existing docs already cover installation, patching, hook verification, reverse engineering, and signing | Deferred new pages: no query/traffic evidence shows which additional pages are needed. Improved inaccurate homepage prerequisites instead. |
| Measure discovery/completion | No authenticated Search Console or usage data was inspected | Deferred analytics, account setup, and instrumentation. No claims about current indexing, traffic, or conversion rates. |
| Use absolute Markdown entry points | Live llms.txt returned relative HTML links | Added absolute per-page Markdown links, prerequisites, task routing, and focused-page guidance. |
| Avoid loading all docs by default | Live llms-full.txt was about 119 KB | Kept full export for consumers that need it; index routes agents to specific pages. Size alone is not a defect. |
| Stop artificial sitemap freshness | sitemap.ts populated every page's lastModified with new Date() | Removed lastModified rather than presenting build time as content-change time. |
| Correct platform claims | Installation said all analysis works on any OS; objc.py invokes lipo and otool, including hook verification during dry-run/no-sign | Replaced blanket claims with command-level requirements. Added a Linux portable-workflow CI smoke stage; it has not run remotely yet. Windows remains unverified. |
| Rich previews and search metadata | Root/per-page metadata, canonical URLs, robots, sitemap, SoftwareSourceCode JSON-LD, and opengraph-image.tsx already existed | **Correction:** these were already implemented. No redundant image or speculative structured data added. The production smoke check caught and fixed the /docs canonical trailing-slash mismatch. |

A further end-to-end check found that relative output paths in documented
commands failed: `zip` interpreted `results/patched.ipa` relative to the
temporary extraction directory. A regression test failed before the fix;
outputs are now resolved before changing cwd. Native zip/unzip diagnostics
are captured and included in operational errors rather than leaking into
JSON stdout. Regression tests cover plain and nested relative destinations
and native-command failure output.

Additional correction: release preparation had incorrectly written
`hooks find --types` in the changelog. The implemented flag is
`hooks verify --types`; the changelog is corrected.

## Live checks before changes

Direct HTTP requests returned 200 for `/`, `/robots.txt`, `/sitemap.xml`,
`/llms.txt`, `/llms-full.txt`, and `/docs/installation.md`. Markdown served
`text/markdown`. Robots allowed crawling and referenced the sitemap.
These checks establish accessibility from this machine, not indexing or
accessibility to every crawler. The web search tool could not open the site;
that failure was not treated as evidence that the site was down.

Google's official guidance says ordinary SEO practices remain relevant to
its AI search features, and llms.txt does not affect Google rankings:
https://developers.google.com/search/docs/fundamentals/ai-optimization-guide
The new agent index is for direct agent consumption; no ranking improvement
is promised.

## Validation

- Python: 342 passed on local macOS/Python 3.12; coverage 85.50% (80% required).
- Ruff lint and formatting: passed. Mypy: passed across 64 source files.
- Distribution: sdist, wheel built from that sdist, and twine metadata checks passed.
- Installed the wheel into a clean environment and ran it from `/tmp`, outside
  the repository. Demo passed with two operations; doctor passed; exported
  schema exactly matched the published artifact. No signing credentials or
  downloads were needed by the demo itself. A second fresh-wheel check also
  passed with relative IPA, definition, asset, and nested output paths.
- Docs: production build passed; link checker reported zero errors; production
  smoke checked homepage metadata, all 13 HTML/Markdown pairs, agent exports,
  schema, robots, sitemap, and missing-Markdown 404 handling.
- Mutation check: changing doctor's all-checks-must-pass logic to any-check-passes
  caused four prerequisite tests to fail. Restored source; tests passed again.
- GUI API tests passed after the setup copy change. No GUI interaction flow
  was redesigned.

Build output includes existing Fumadocs CSS pseudo-element warnings and a
Node module.register deprecation notice. Python tests include the existing
Starlette/httpx deprecation notice and expected version-mismatch warnings.
No dependency upgrades were made in this work.

## Limits and deferred work

- GitHub Actions and the production deployment cannot validate the new commits
  until they are pushed. No push, deployment, or release is part of this pass.
- Linux workflow checks are configured, not yet executed in Linux here.
- New commands are unreleased source changes. The package version remains
  0.2.0; do not upload the local build as a replacement for the existing release.
- No real-device install, signing credential audit, search ranking assessment,
  Search Console setup, or analytics collection was performed.
- Remaining text-only hook/analysis commands can gain JSON separately with
  their own compatibility review; existing consumers retain their formats.
