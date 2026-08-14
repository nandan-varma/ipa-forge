#!/usr/bin/env python3
"""Generate the `hooks:` manifest for a patch definition from tweak sources.

Scans dylib/*.m for runtime hook calls (ytfHookInstance/ytfHookClass/
ytfAddInstanceMethod) and emits the YAML `hooks:` list, marking a curated set
of load-bearing hooks as `required: true` (sign-in, adblock core, settings
backbone) so `forge patch --dry-run` fails loudly if a future app version
breaks them.

Usage:
    python3 tools/generate_hooks_manifest.py  # prints YAML (copy into youtube.yaml)
"""

import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE.parent / "dylib"

# (class, selector) pairs whose failure means a core feature silently dies.
REQUIRED = {
    # sign-in (OAuth + keychain)
    ("SSORPCService", "URLFromURL:withAdditionalFragmentParameters:"),
    ("SSOKeychainHelper", "accessGroup"),
    ("SSOKeychainHelper", "sharedAccessGroup"),
    ("SSOConfiguration", "initWithClientID:supportedAccountServices:"),
    ("NSBundle", "bundleIdentifier"),
    ("NSBundle", "infoDictionary"),
    ("NSFileManager", "containerURLForSecurityApplicationGroupIdentifier:"),
    # adblock
    ("YTAdShieldUtils", "spamSignalsDictionary"),
    ("YTAdsInnerTubeContextDecorator", "decorateContext:"),
    ("YTAccountScopedAdsInnerTubeContextDecorator", "decorateContext:"),
    ("YTLocalPlaybackController", "createAdsPlaybackCoordinator"),
    ("YTPlayerResponse", "playerAdsArray"),
    ("YTPlayerResponse", "adSlotsArray"),
    ("YTIElementRenderer", "elementData"),
    ("YTInnerTubeCollectionViewController", "displaySectionsWithReloadingSectionControllerByRenderer:"),
    ("YTInnerTubeCollectionViewController", "addSectionsFromArray:"),
    ("_ASDisplayView", "didMoveToWindow"),
    ("YTReelDataSource", "setReels:"),
    # settings UI
    ("YTSettingsGroupData", "orderedCategories"),
    ("YTAppSettingsPresentationData", "settingsCategoryOrder"),
    ("YTSettingsSectionItemManager", "updateSectionForCategory:withEntry:"),
}

CALL_RE = re.compile(
    r"(ytfHookInstance|ytfHookClass|ytfAddInstanceMethod)\(\s*"
    r"NSClassFromString\(\@\"([^\"]+)\"\)\s*,\s*"
    r"(?:@selector\(([^)]+)\)|sel_registerName\(\"([^\"]+)\"\))"
)
KIND_FOR = {"ytfHookInstance": "instance", "ytfHookClass": "class", "ytfAddInstanceMethod": "instance"}


def main() -> None:
    hooks: list[tuple[str, str, str, bool]] = []  # (class, selector, kind, added)
    for f in sorted(SRC.glob("*.m")):
        text = f.read_text(errors="replace")
        for m in CALL_RE.finditer(text):
            fn, cls, sel1, sel2 = m.groups()
            sel = sel1 or sel2
            added = fn == "ytfAddInstanceMethod"
            hooks.append((cls, sel, KIND_FOR[fn], added))

    # de-duplicate, keep insertion order
    seen: set[tuple[str, str]] = set()
    rows = []
    for cls, sel, kind, added in hooks:
        if (cls, sel) in seen:
            continue
        seen.add((cls, sel))
        rows.append((cls, sel, kind, added))

    out = ["hooks:"]
    for cls, sel, kind, added in rows:
        required = (cls, sel) in REQUIRED
        flags = f"    kind: {kind}"
        if added:
            flags += "\n    added: true"
        if required:
            flags += "\n    required: true"
        out.append(f'  - class: "{cls}"')
        out.append(f'    selector: "{sel}"')
        out.append(flags)
    print("\n".join(out))
    print(f"\n# {len(rows)} hooks ({sum(1 for r in rows if (r[0], r[1]) in REQUIRED)} required)", file=sys.stderr)


if __name__ == "__main__":
    main()
