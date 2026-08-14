# YouTube Pro v0.0.4 — device test sheet

Install `/Users/nandan/dev/ytlite-ipa/Youtube_pro_v0.0.4.ipa`. Confirm build:
Settings → YTFreedom → version row = **v0.8.0**.

## What changed in v0.0.4 (fixes the three broken items)

- **Video quality + Playback speed menu items fixed**: the old code replaced
  their handlers with selectors that don't exist in 21.32.4 and disabled the
  items — tapping them did nothing. The replacement hook is removed; the app's
  own menu actions now open the sheets.
- **Old quality picker**: forced `enableQuickMenuVideoQualitySettings -> NO`
  (real dynamic property — the %new installs), so the quality sheet is the
  classic list, not the thumbnail picker.
- **Extra speeds**: the varispeed sheet keeps the 13-rate option list
  (0.25x-10x) + 10x cap; with the menu item working again the sheet actually
  opens.
- **Default tab fixed**: `selectItemWithPivotIdentifier:` doesn't exist in
  21.32.4 (selref-only) — the old call silently no-opped. Now hooked on the
  app's own `YTAppPivotBarController defaultSelectedPivotIdentifier`
  getter+setter, so our choice is what the app selects when the bar loads.
  Library/You still picks whichever the server sent.

## What changed in v0.0.3 (structure)

- **Full audit vs the 21.32.4 IPA**: 159/159 hook targets resolve against the
  binary (otool + strings). Nothing targets an old tweak.
- **Settings rebuilt from a single source of truth** — the feature catalog in
  `dylib/YTFFeatures.m` (one row per setting: key, title, group, default,
  restart, beta). Defaults register from it, the UI renders from it, the
  restart hints come from it. Adding/removing a feature = one table row.
- **Curated top sections** (what a regular user touches): Player, Appearance,
  Shorts, Feed, Navigation, Tab bar.
- **Player is now minimal**: Background playback, Old quality picker, Extra
  speeds, Mute button, Gesture controls + HUD, plus two dropdowns for which
  control each edge swipe adjusts (Brightness / Volume / Speed). All ON by
  default.
- **Everything else moved under Advanced** (bottom): Advanced player (beta —
  may work), A/B Testing, Menu items, System, Beta. Future section shows
  disabled rows: Downloads, Native share, Dislike counts, SponsorBlock.
- **Downloads disabled** (was not implemented): section removed from settings,
  listed under Future.
- **Fixed a linker bug**: non-ASCII characters (—, …) silently dropped string
  literals from the dylib (blank row titles). All UI strings are ASCII now.
- **Not-everything-is-a-toggle**: Default tab and edge-swipe sides are now
  checkmark pickers (dropdown-style), not switches.

## 0. Smoke (1 min)

1. Launch, no crash. Settings → YTFreedom shows rows in order:
   Player, Appearance, Shorts, Feed, Navigation, Tab bar, Advanced, Preferences.
2. Open Player: 8 rows — 5 toggles ON (background, old quality, extra speeds,
   mute, gestures), Gesture HUD ON, Left/Right edge swipe rows.
3. Open Advanced → A/B Testing: flip one → "Restart to apply" pill.
4. Audio keeps playing with screen off.

## 1. Always-on (no toggle)

- Ads: 3 videos + Home scroll + 3 Shorts → zero ads.
- Sign-in: signed in, survives relaunch.

## 2. Player (curated — the defaults you chose)

| Item | Test | Works = | Broken = |
| --- | --- | --- | --- |
| Background playback | Play → lock screen | Audio continues | Stops |
| Old quality picker | ⋯ → Video quality | Opens the CLASSIC list picker | Thumbnail picker opens / nothing |
| Extra speeds | ⋯ → Playback speed | Sheet opens with 13 rates up to 10× | Only stock rates / sheet doesn't open |
| Mute button | Fullscreen | Mute icon in control row | No mute icon |
| Gesture controls | Fullscreen, swipe left/right edges | Brightness (left) / volume (right) HUD | Nothing |
| Left/Right edge swipe | Change Right to Speed, swipe right | Speed changes | No effect |
| Gesture HUD | Toggle off, gesture | No HUD overlay | HUD still shows |

## 3. Appearance / Shorts / Feed / Navigation / Tab bar

- Appearance: OLED theme (restart), OLED keyboard (restart).
- Shorts: hide like/dislike/comment/share (icon-filtered), hide metadata,
  enable quality selector.
- Feed: hide channel filter bar, hide Shorts shelf, hide search history,
  hide related videos.
- Navigation: hide logo, premium logo (ON), hide notification/search/voice/
  cast (cast ON = hidden), sticky navbar.
- Tab bar → Default tab: pick Home / Shorts / Subscriptions / Library / You,
  relaunch, confirm the app opens there. You = the FEaccount tab. (v0.0.4:
  selection now goes through the app's own YTAppPivotBarController.)

## 4. Advanced (power user)

- **Advanced player** — 35 demoted toggles, each labeled (beta). Test the ones
  you care about; report works/broken per item.
- **A/B Testing** — verified server-config flags; flip + relaunch (restart pill
  shows).
- **Menu items** — remove Download/Watch later/Save to playlist/Share/Not
  interested/Don't recommend/Report from ⋯ menu.
- **System** — upgrade dialogs, "Are you there?", snackbar, startup
  animations, Play-next-in-queue, silent votes, rate prompts (ON), HUD
  messages.
- **Beta** — unverified targets; report per item so each is rewired or dropped.
- **Future** — disabled rows (Downloads, Native share, Dislike counts,
  SponsorBlock) — do nothing by design.

## 5. Preferences

Import / Export / Restore defaults / Clear cache / Auto-clear cache (ON).

## Report format

```
Player: all work except gesture speed side (no change); HUD ok
Advanced-player: tap-to-seek works; heatmap broken (still shows)
```

Plus the launch log if something is broken:
`log stream --predicate 'subsystem == "com.nandan.ytfreedom"'`
