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

import sys
from pathlib import Path

from ipa_forge.hooks.scan import scan_hook_sources

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


def main() -> None:
    """Generate the `hooks:` manifest from dylib sources.

    Uses ipa_forge's scanner, which understands inline NSClassFromString,
    local-variable classes, resolver helpers, sel_registerName, and
    ytfHookConfigBool. --inplace <yaml> writes the block into the patch
    definition instead of printing it.
    """
    decls = scan_hook_sources(SRC)
    if not decls:
        print("no hooks found", file=sys.stderr)
        return

    out = ["hooks:"]
    for d in decls:
        out.append(f'  - class: "{d.class_name}"')
        out.append(f'    selector: "{d.selector}"')
        out.append(f"    kind: {d.kind}")
        if d.added:
            out.append("    added: true")
        if (d.class_name, d.selector) in REQUIRED:
            out.append("    required: true")

    if "--inplace" in sys.argv:
        idx = sys.argv.index("--inplace")
        target = Path(sys.argv[idx + 1])
        text = target.read_text()
        head = text.split("\nhooks:\n", 1)[0]
        target.write_text(head + "\n" + "\n".join(out) + "\n")
        print(f"wrote {len(decls)} hooks into {target}", file=sys.stderr)
        return

    print("\n".join(out))
    print(
        f"\n# {len(decls)} hooks ({sum(1 for d in decls if (d.class_name, d.selector) in REQUIRED)} required)",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
if __name__ == "__main__":
    main()
