# Adding a feature to a hook dylib

The conventions every feature follows across the three patch sets
(YouTube, Spotify, Instagram — see [`STATE.md`](../STATE.md) for current
status). Adding a feature is: a key, a default, a settings row, an
implementation in the right file, and a hooks declaration — in that order.

## 1. The key

Every user-facing feature is a `NSUserDefaults` key. Each patch set has its
own prefix and enabled-check macro, same shape every time:

| Patch set | Key prefix | Enabled-check macro |
| --- | --- | --- |
| YouTube | `YTFreedom` | `IS_ENABLED(key)` |
| Spotify | `SpotifyMod` | `smEnabled(key)` |
| Instagram | `IGMod` | `igEnabled(key)` |

Declare it in the shared header (`dylib/<App>Hook.h`):

```objc
#define kSMNewFeature @"SpotifyModNewFeature"
```

## 2. The default

Register the default in the constructor (`dylib/<App>Hook.m`), inside the
`registerDefaults:` dictionary (YouTube: the `YTFFeatureSpec` catalog in
`YTFFeatures.m` is the single source of truth instead — see its own header
comment). New features default **ON** unless there is a reason not to (e.g.
a behavior change users might not want) — **with one standing exception**:
a feature built via RE with no reference source to check against and no
on-device confirmation yet defaults **OFF** and is labeled beta in the
settings row (YouTube's native share/RYD dislikes/custom downloads are the
precedent). Flip it to default-ON once a device pass confirms it works.

## 3. The implementation

- One file per feature area; add the feature to the matching file
  (`AdBlock.m`, `SessionProtection.m`, `PremiumPatch.m`, `Settings.m`, …) or
  create a new `Feature.m`.
- Gate it on the key at the top of its init:

```objc
void SpotifyNewFeatureInit(void) {
    if (!smEnabled(kSMNewFeature)) { os_log(spotLog(), "...: disabled"); return; }
    // hooks...
}
```

- **One hook per method across the dylib.** If your feature needs a method
  another feature already hooks (e.g. `_ASDisplayView didMoveToWindow`,
  the player-overlay insertion), put the logic in the existing owner file and
  call a shared helper — a second `hookInstance` on the same method silently
  replaces the first.
- **No local reference source for the internal API you need, or the object
  graph is too deep/uncertain to hardcode an accessor chain?** Don't guess
  property names. Do a bounded breadth-first walk of the object graph from
  a known, reachable anchor (a touched view, the current player VC) —
  collect anything whose *shape* matches what you need (responds to the
  right selectors), not anything with a specific class/property name. This
  survives internal renames the same way a hardcoded chain wouldn't.
  Instagram's `MediaDownload.m` and YouTube's `DownloadCore.m` are the two
  worked examples — copy their walker, don't reinvent it.
- Verify the target exists before writing it:
  `forge hooks extract --ipa <ipa> --class <Class>` / `--search <regex>`,
  and cross-check suspicious selectors with `strings` (the parser
  under-reports GPBMessage methods).
- Prefer pure ObjC-runtime swizzling. **No C-level rebinding** (fishhook-style)
  unless unavoidable — it was the crash source in the Spotify port; if you
  must, defer it past launch and guard every resolved original pointer.
- Wrap the init in the existing `@try`-isolation so a failure degrades.

## 4. The settings row

Add the toggle to the in-app settings screen. Title + one-line detail + the
key. The screen already says "changes apply on relaunch" (toggles are read
at hook-install time). Each patch set's settings UI lives in its own file
and shape:

| Patch set | File | Mechanism |
| --- | --- | --- |
| YouTube | `YTFFeatures.m` / `SettingsUI.m` | catalog-driven — add one `YTFFeatureSpec` row; `SettingsUI.m` renders groups/rows from it automatically, no manual wiring |
| Spotify | `SettingsUI.m` | `SMFeature` list |
| Instagram | `SettingsUI.m` | hand-built rows (long-press home tab / 4-finger hold to reach) |

## 5. The hooks declaration

Add the new hook target(s) to the definition's `hooks:` block
(`<app>.yaml`). If the hook is load-bearing (feature silently dies when
the class/selector is renamed in a future app version), mark
`required: true`. Regenerate or hand-update:

```bash
forge hooks manifest --dir dylib/ --required hooks-required.txt   # direct calls
# helper/loop-based hooks: hand-declare in the yaml
```

**Don't skip this even for a hook that "obviously" won't drift.** Confirm
nothing was missed with `forge hooks audit --ipa <ipa> --dir dylib/ --patches
<app>.yaml` — it fails (exit 1) if any hook the source calls isn't in the
`hooks:` block yet. This is a real, recurring mistake, not a hypothetical:
it's how three real hooks were found missing from Spotify's and three more
from Instagram's `hooks:` block after the fact, in both cases with
`--dry-run` passing the whole time because the gap is invisible to it by
construction.

## 6. Verify + commit

```bash
dylib/build.sh
forge hooks audit --ipa <base>.ipa --dir dylib/ --patches <app>.yaml
# -> all source hooks declared, 0 undeclared (see step 5)
forge patch --ipa <base>.ipa --patches <app>.yaml --dry-run
# -> must show the new hook attach (or an honest unverified for system APIs)
forge patch --ipa <base>.ipa --patches <app>.yaml --no-sign --output <out>.ipa
```

Then: device test (the `com.nandan.<app>mod` os_log shows the feature's
`ready`/`disabled` line). If a device isn't available yet, default the
feature OFF and mark it beta in the settings row instead of skipping it
(see step 2) — don't claim it works before it's confirmed. Update the
patch set's `README.md` feature list, and commit — **including the patch
submodule itself** (`patches/<app>/` is a separate git repo; commit and
push there too, then commit the updated submodule pointer in the main
repo).

## Debugging a feature that doesn't work

1. Does the hook attach? The install log prints every
   `hooked -[Class method]` line.
2. Does the code path fire? Add an os_log in the block.
3. Is it a server/A-B surface? Config-flag hooks
   (`ytfHookConfigBool`-style) chain to the server value when off — log the
   effective value.
4. Is it a hook-point drift? `forge hooks diff --old <old>.ipa --new <new>.ipa
   --patches <yaml>` shows what regressed between versions.

## Related

- [`adding-an-app.md`](adding-an-app.md) — end-to-end porting
- [`patch-reference.md`](patch-reference.md) — the YAML contract
- [`README.md`](README.md) — docs index
