# Adding a feature to a hook dylib

The conventions every feature follows in the two patch sets. Adding a feature
is: a key, a default, a settings row, an implementation in the right file,
and a hooks declaration — in that order.

## 1. The key

Every user-facing feature is a `NSUserDefaults` key (prefix `SpotifyMod` /
`YTFreedom`; both use `smEnabled(key)` / `IS_ENABLED(key)` which default to
ON). Declare it in the shared header (`dylib/<App>Hook.h`):

```objc
#define kSMNewFeature @"SpotifyModNewFeature"
```

## 2. The default

Register the default in the constructor (`dylib/<App>Hook.m`), inside the
`registerDefaults:` dictionary. New features default **ON** unless there is a
reason not to (e.g. a behavior change users might not want).

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
- Verify the target exists before writing it:
  `forge hooks extract --ipa <ipa> --class <Class>` / `--search <regex>`,
  and cross-check suspicious selectors with `strings` (the parser
  under-reports GPBMessage methods).
- Prefer pure ObjC-runtime swizzling. **No C-level rebinding** (fishhook-style)
  unless unavoidable — it was the crash source in the Spotify port; if you
  must, defer it past launch and guard every resolved original pointer.
- Wrap the init in the existing `@try`-isolation so a failure degrades.

## 4. The settings row

Add the toggle to the in-app settings screen (`dylib/Settings.m` — the
`SMFeature` list or the equivalent YouTube settings builder). Title +
one-line detail + the key. The screen already says "changes apply on relaunch"
(toggles are read at hook-install time).

## 5. The hooks declaration

Add the new hook target(s) to the definition's `hooks:` block
(`<app>-mod.yaml`). If the hook is load-bearing (feature silently dies when
the class/selector is renamed in a future app version), mark
`required: true`. Regenerate or hand-update:

```bash
forge hooks manifest --dir dylib/ --required hooks-required.txt   # direct calls
# helper/loop-based hooks: hand-declare in the yaml
```

## 6. Verify + commit

```bash
dylib/build.sh
forge patch --ipa <base>.ipa --patches <app>-mod.yaml --dry-run
# -> must show the new hook attach (or an honest unverified for system APIs)
forge patch --ipa <base>.ipa --patches <app>-mod.yaml --no-sign --output <out>.ipa
```

Then: device test (the `com.nandan.<app>mod` os_log shows the feature's
`ready`/`disabled` line), update the patch set's `README.md` feature list,
and commit.

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
