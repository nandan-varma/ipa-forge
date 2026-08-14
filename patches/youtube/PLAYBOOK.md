# Playbook — from a new YouTube IPA to a working mod

> The generic "port a new app" procedure lives in
> [`ipa-forge/docs/adding-an-app.md`](../../docs/adding-an-app.md) and the
> per-feature conventions in
> [`ipa-forge/docs/adding-a-feature.md`](../../docs/adding-a-feature.md).
> This file is the YouTube-specific application.

This is the complete runbook for future sessions. Given any YouTube IPA, this
is the loop to follow — no prior knowledge required. Everything referenced
here lives in this repo and is kept up to date.

## 0. Where everything lives

| Path | What it is |
| --- | --- |
| `/Users/nandan/dev/ipa-forge` | The patcher (generic). `forge` CLI, `ipa_forge/hooks/` hook engine, docs/ |
| `/Users/nandan/dev/ipa-forge/patches/youtube/` | This patch set (YouTube-specific) |
| `…/youtube.yaml` | The canonical patch definition (ops + `hooks:` block) |
| `…/dylib/` | Hook dylib sources (`build.sh` compiles all `*.m` → `assets/libYTHook.dylib`) |
| `…/assets/` | Staged dylib + swapped resources (90s video) |
| `…/tools/generate_hooks_manifest.py` | Regenerates the `hooks:` block from dylib sources |
| `…/ROADMAP.md` | Goal-by-goal status and deferred-work detail |
| `…/SOURCES.md` | Attribution for every feature (YouMod/YTLite/uYouPlus/…) |
| `/Users/nandan/dev/ytlite-ipa/` | Working dir: base IPAs, built outputs, YTLite source checkout |
| `/Users/nandan/dev/YouModIpa/` | Reference prebuilt mod (YouMod v1.3.0) + its decrypted base |
| `/tmp/youmod-src`, `/tmp/uyoue`, `/tmp/ytlite-latest` | Reference source checkouts (reclone if missing) |

## 1. The standard delivery loop

```
1. Receive IPA (or the user sideloads the current build and reports)
2. Diagnose -> fix -> rebuild -> deliver
3. Repeat until clean
```

### Build & deliver (21.32.4 — everything verified)

```bash
# one-shot: rebuild dylib, dry-run (hooks gate), build unsigned IPA
cd /Users/nandan/dev/ipa-forge && source .venv/bin/activate
patches/youtube/dylib/build.sh
forge patch --ipa <base.ipa> --patches patches/youtube/youtube.yaml \
  --output /Users/nandan/dev/ytlite-ipa/YouTubeMod_21.32.4_unsigned.ipa \
  --dry-run                 # must show "Hooks: N/N attach" with no required failures
forge patch --ipa <base.ipa> --patches patches/youtube/youtube.yaml \
  --no-sign --output /Users/nandan/dev/ytlite-ipa/YouTubeMod_21.32.4_unsigned.ipa
```

Base IPA: `com.google.ios.youtube_21.32.4_und3fined.ipa` (decrypted, thin
arm64 — the App-Store-shaped `*_544007664_*.ipa` is **encrypted** and cannot
be used; forge will still dry-run but the app won't run).

The mod installs unsigned via AltStore (AltStore signs at install with your
Team ID). Keep `--no-sign`.

### Device debugging

- **Hook attach report**: every hook logs at launch →
  `log stream --predicate 'subsystem == "com.nandan.ytfreedom"'`
  (or Console.app). If a toggle does nothing, the first question is always
  "did the hook attach?" — the launch log answers it.
- **Server/A-B suspicion**: YouTube's UI is server/hot-config driven. The
  Shorts action-rail diagnostic logs the exact buttons the server sent
  (`reel action bar buttons from server:`). Config-flag toggles
  (`ytfHookConfigBool`) override the client side of A/B and chain to the
  server value when off.
- **Settings**: everything is under Settings → **YTFreedom** (8 groups, ~70
  toggles). Defaults register in `dylib/YTFreedom.m`.

## 2. Porting to a NEW YouTube version (the critical path)

When the user supplies a different version (e.g. 22.x), do NOT patch
blindly — the version gate (`target.version.exact`) will refuse anyway, and
silent hook no-ops are the #1 failure mode. The `hooks:` block turns that
into a report:

```bash
# 1. Put the decrypted IPA on disk (e.g. /Users/nandan/dev/ytlite-ipa/)
# 2. Bump target.version in youtube.yaml (exact: "<new>")
# 3. Dry-run — this now verifies every hook against the new binary:
forge patch --ipa <new.ipa> --patches youtube.yaml --output /tmp/x.ipa --dry-run
#    -> "Hooks: N/M attach (K issue(s))" — every issue is a hook that would no-op
# 4. For each issue, find what replaced the class/selector:
forge hooks extract --ipa <new.ipa> --search "<substring of old class name>"
#    reverse lookup: which classes implement a selector (and is it real or
#    referenced-only - no IMP to swizzle?):
forge hooks find didPressVarispeed: --ipa <new.ipa>
# 5. Fix the dylib source (rename/redirect the hook), rebuild, re-run dry-run
# 6. When required hooks are green, regenerate the manifest and commit:
python3 tools/generate_hooks_manifest.py   # -> copy `hooks:` into youtube.yaml
```

Status vocabulary (`ipa_forge/hooks/verify.py`): `ok` / `ok-inherited` /
`ok-system` / `added` (the tweak provides it — absence expected) /
`unverified` (class/selector exists but parser couldn't fully confirm —
verify once on device) / `missing-class` / `missing-selector` / `elsewhere`
(the real failures — `required: true` blocks the run).

Rules of thumb when porting:

- **The parser under-reports**: methods on GPBMessage subclasses and some
  REL-flag method lists don't decode. Cross-check any flagged selector with
  `strings <binary> | grep -cx "<selector>"` before changing code.
- **System inheritance is fine**: `setHidden:`, `setFrame:`, `titleLabel`,
  `layoutSubviews` etc. attach through UIView/UIButton — the verifier knows.
- **`added: true` hooks** (`playerAdsArray`, `adSlotsArray`,
  `enableSkippableAd`, `maximumPlaybackRate`, `isBackgroundEnabled`,
  `hasMinimizedEndpoint`/`hasPlaybackMode`,
  `enableQuickMenuVideoQualitySettings`, `updateYTFreedomSectionWithEntry:`,
  gesture-delegate methods) are load-bearing: if selrefs still reference the
  selector, the app is calling into a hole the add fills — keep them.
- **Extensions are always stripped** (AltStore bundle-id suffix breaks their
  ids — `IXErrorDomain Code=2`). Never re-add `Extensions/`/`PlugIns/`.
- **OAuth safety page** ("Google can't confirm that it's safe") is fixed by
  the `SSORPCService URLFromURL:withAdditionalFragmentParameters:` fingerprint
  strip — if sign-in breaks on a new version, that's the first hook to check.

## 3. Research playbook (new features / UI changes)

When asked to "research the new IPA", the repeatable passes are:

1. **Hook surface**: `forge hooks audit --ipa <ipa> --dir dylib/` — what of
   ours still attaches.
2. **Config flags**: dump `YTColdConfig`/`YTHotConfig` getters with
   `forge hooks extract --ipa <ipa> --class YTColdConfig --limit 0`, filter
   for `enable/disable/show/hide … player|shorts|menu|miniplayer`. Flip
   client-side UX wins via `ytfHookConfigBool` (never blindly — only
   self-contained UI flags).
3. **Reference diffs**: reclone YouMod / uYouEnhanced / YTLite latest into
   `/tmp/`, diff their `%hook` class lists against ours, port what exists in
   the new binary.
4. **UI identity**: accessibility-identifier strings (`strings <binary> |
   grep -E '^id\\.'`) tell you what id-based hiding can target. The ELM
   (Element) framework renders most modern UI — protobuf renderers, not
   UIView subclasses, so id-hiding often needs the renderer path instead.

## 4. Remaining goals (see ROADMAP.md for full detail)

| Goal | State | Next step |
| --- | --- | --- |
| G15 Native share | blocked | protobuf extension-root API drift — needs field-number re-derivation or a direct watch-URL approach |
| G16 RYD dislikes | researched | force-inject needs protobuf construction of a dislike renderer + `YTIDislikeEndpoint`; diagnostic hook already logs the server's action bar |
| G17 Downloads | not started | sub-plan in ROADMAP: button → format picker → auth → NSURLSession core → manager/Photos (YouMod's Download.x is self-contained) |
| On-device pass | pending | sideload current build, check Settings → YTFreedom toggles, send os_log lines for anything not working |

## 5. Conventions (keep them)

- One hook per method across the dylib. Shared surfaces (`_ASDisplayView`,
  `YTInnerTubeCollectionViewController`, player-overlay insertion) are owned
  by single files — don't re-hook them in two places (later hooks silently
  replace earlier ones).
- Every hook target goes in the `hooks:` block (required = load-bearing).
- New toggles: key macro in `YTFreedom.h`, default in `YTFreedom.m`, row in
  `SettingsUI.m`, implementation in the area `.m` — in that order.
- Commit per goal; update ROADMAP status + SOURCES attribution with it.
