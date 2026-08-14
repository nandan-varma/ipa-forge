# Playbook — Instagram 442.0.0 (IGMod)

The Instagram-specific runbook. The generic procedure lives in
[`ipa-forge/docs/adding-an-app.md`](../../docs/adding-an-app.md); this file
is the concrete application.

## Where everything lives

| Path | What it is |
| --- | --- |
| `instagram.yaml` | The definition (strip Extensions/PlugIns + stage + weak link + `hooks:`) |
| `dylib/` | IGModHook sources: `IGModHook.h/.m` (plumbing + settings keys), `Helpers.m` (toast + share), `AdBlock.m`, `StoryPrivacy.m`, `MediaDownload.m`, `CopyText.m`, `SafeMode.m`, `SettingsUI.m` |
| `dylib/.clangd` | LSP sysroot config so clangd can resolve UIKit for these sources |
| `/Users/nandan/Downloads/com.burbn.instagram_442.0.0_und3fined.ipa` | Base IPA (decrypted) |

## Build & deliver

```bash
cd /Users/nandan/dev/ipa-forge && source .venv/bin/activate
patches/instagram/dylib/build.sh              # -> build/IGModHook.dylib
forge patch --ipa /Users/nandan/Downloads/com.burbn.instagram_442.0.0_und3fined.ipa \
  --patches patches/instagram/instagram.yaml \
  --output /tmp/x.ipa --dry-run                      # hooks gate (32/32 attach)
forge patch --ipa /Users/nandan/Downloads/com.burbn.instagram_442.0.0_und3fined.ipa \
  --patches patches/instagram/instagram.yaml \
  --no-sign --output /Users/nandan/dev/ytlite-ipa/IGMod_v0.0.1_unsigned.ipa
```

Bump `IGMOD_VERSION` in `dylib/IGModHook.h` and the IPA file name on every
pass (v0.0.1, v0.0.2, ...); the settings About section shows the same
version.

## Features (all toggleable in IGMod settings, default ON)

Settings are reached by **long-pressing the home tab button** or a
**4-finger hold anywhere** (both entry points hook-verified; the 4-finger
hold is the drift-proof fallback).

- **Feed** — Hide ads, Hide stories tray, No suggested posts, No suggested
  reels, No suggested accounts.
- **Privacy** — No story seen receipt, No typing indicator, No screenshot
  alerts (all default OFF except screenshot alerts, ON).
- **Media** — Save feed posts (long-press), Save stories (long-press), Save
  profile pictures (long-press), Copy captions (long-press).
- **Misc** — Disable safe mode, Home-tab settings shortcut, 4-finger
  settings hold.

## The load model (why it doesn't crash)

Plain ObjC-runtime swizzling only (`class_replaceMethod`), same as the
YouTube/Spotify sets. The constructor is inert — hooks install on the main
run loop after launch, `@try`-isolated per feature, and the dylib is
`LC_LOAD_WEAK_DYLIB` (a load failure degrades instead of aborting).

## Debugging

`com.nandan.igmod` os_log subsystem: watch for `hooked -[…]` at install and
`<feature> ready|failed`. A missing hook logs `inst <sel> not found on
<class>` — that is the version-drift canary.

## Porting to a newer Instagram

1. New decrypted IPA → bump `target.version` in `instagram.yaml`.
2. `forge patch --dry-run` → the hooks report shows what broke. For fast
   iteration, point the hooks commands at the already-extracted bundle
   (`--app-dir Payload/Instagram.app`) instead of re-extracting the 300MB
   IPA every time.
3. `forge hooks diff --old 442.0.0.ipa --new <new>.ipa --patches instagram.yaml`
   — exact regressions. A class/selector the walk misses but whose string is
   still in the binary reports `unverified` (parser gap), not `missing-class`.
4. Fix the dylib sources, rebuild, regenerate the hooks block
   (`forge hooks manifest --dir dylib/`) plus the hand-declared
   helper/loop hooks (the `*AdsResponseParser` loop and the
   `didMoveToSuperview` long-press attach points).
5. Rebuild + deliver. Re-verify the media-accessor selectors
   (`IGMedia -photo/-video`, `IGVideo -allVideoURLs`,
   `IGPhoto -imageURLForWidth:`, `IGUser -derivedProfilePicURL`) — those are
   resolved at runtime with `respondsToSelector` guards, so a rename only
   degrades that one feature instead of failing the run.
