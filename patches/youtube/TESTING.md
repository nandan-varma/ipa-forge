# YouTube Pro v0.0.2 (r2) — device test sheet

Install `/Users/nandan/dev/ytlite-ipa/Youtube_pro_v0.0.2.ipa` (replaced). Confirm
you have the new build: Settings → YTFreedom → top row must read **YTFreedom v0.6.0**.

**What changed in r2 (all extracted from the binary, otool/strings-verified):**

- **A/B Testing** now only contains flags whose selectors exist on the config
  classes in 21.32.4 (14 verified via otool). Dropped "Animated previews"
  (dead selector). ALL of them now show the **Restart to apply** pill — the
  config values are read at launch, so flip → relaunch → test.
- **New Beta section** (sparkle icon): toggles whose targets are absent from
  the 21.32.4 binary (ids/selectors that existed in other versions' tweaks).
  They're kept so nothing is lost — flip, test, and report so each gets
  rewired to a real target or dropped.
- **Watch-page action bar fixed**: like/dislike/share/save/download are now
  hooked on the real view class (`YTSlimVideoDetailsActionView`) which covers
  BOTH the slim and scrollable button-row variants you saw. Clip/remix buttons
  don't exist on the watch page in 21.32.4 → moved to Beta.
- **You tab**: Default tab gained a **You** option; "Library" now auto-selects
  the You tab when the server sends it (FEaccount) and Library (FElibrary)
  otherwise — both variants handled.
- **Shorts rail**: like/dislike/share/comment are now filtered by icon type
  (the rail is server-driven, no a11y ids in 21.32.4). The launch log prints
  `reel action bar buttons (after filter): icon=… aid=…` — send it for any
  button that doesn't hide.

Global rules:

- Per toggle report exactly one of: **works / broken / n/a**.
- When the **Restart to apply** pill appears, relaunch before judging.
- If a toggle is broken AND its hook line is missing from
  `log stream --predicate 'subsystem == "com.nandan.ytfreedom"'`, it's a hook
  problem, not a logic problem — send the launch log.

## 0. Smoke (2 min)

1. Launch → no crash. Settings → YTFreedom shows: Downloading, Appearance,
   Navigation bar, Feed, Player, A/B Testing, Shorts, Tab bar, Miscellaneous,
   Menu items, **Beta**, Preferences. Version row = v0.6.0.
2. Flip any A/B toggle → "Restart to apply" pill appears and fades.
3. Audio keeps playing with screen off (Background playback ON by default).

## 1. Always-on: ads / sign-in (no toggle)

- **Ads**: 3 random videos (skip first 30s), 2 min Home scroll, 3 Shorts, one
  video to end screen → zero ads. (Was clean in r1 — just confirm still clean.)
- **Sign-in**: signed in, survives force-quit. (Was clean in r1.)

## 2. A/B Testing (all show restart pill — relaunch after each flip)

| Toggle | Test | Works = | Broken = |
| --- | --- | --- | --- |
| Mute button in player | Fullscreen, restart | Mute icon in control row | No mute icon |
| Inline chapter seek | Restart, tap a chapter chip | Seeks to chapter | Only opens chapter list |
| Pinch to fullscreen | Restart, pinch out | Fullscreen | Nothing |
| Reduce player overlays | Restart, open Settings | "Reduce overlays" visible | Not present |
| High-quality audio setting | Restart, open Settings | Audio-quality picker | Not present |
| Shorts seekbar | Restart, play a Short | Progress bar visible | No seekbar |
| Shorts speed from ⋯ menu | Restart, Short ⋯ menu | Speed options apply | No speed menu |
| Inline Shorts shelf playback | Restart, Home Shorts shelf | Shorts play inline | Opens player |
| Disable Shorts PiP | Restart, Short → background | No PiP | PiP appears |
| Disable new miniplayer | Restart, minimize player | Classic miniplayer | New-style miniplayer |

## 3. Watch-page action row (between title and comments — both variants)

| Toggle | Test | Works = | Broken = |
|---|---|---|---|
| Hide like / dislike / share / save / download | Watch a video, check the button row under the title (variant 1: single row, variant 2: scrollable) | Button gone in BOTH variants | Still visible in either variant |

## 4. Player (rest of group)

> Defaults ON: Old quality picker, Gesture controls. Restart-pill items:
> Tap-to-seek, Hide heatmap, Old quality picker, Extra speeds.

Test the untested ones: Hide autoplay/captions/cast/prev/next, rewind-ffw,
remove dark overlay, endscreen cards, suggested video, paid promo, watermark,
gesture controls, double-tap/long-press, exit fullscreen, auto-disable
captions, remaining-time toggles, fullscreen actions/title, stop autoplay,
content warning, auto/portrait fullscreen, old quality picker, extra speeds,
tap-to-seek, heatmap, pull-to-fullscreen, red progress bar, timestamped link,
hints, force miniplayer, always show seekbar.

## 5. Shorts (slim group now)

| Toggle | Test | Works = | Broken = |
| --- | --- | --- | --- |
| Hide like / dislike / share / comment | Play a Short, check right rail, restart once | Button gone | Still there (send log) |
| Hide metadata button | Short, top-right | Pivot/meta button gone | Still there |
| Enable quality selector | Short ⋯ menu | Quality option | No quality option |

## 6. Feed

| Toggle | Test | Works = | Broken = |
| --- | --- | --- | --- |
| Hide sub bar | Home/Subs top | Chip bar gone | Chips show |
| Hide Shorts shelf | Home | Shorts row gone | Row shows |
| Hide search history | Tap search field | No recent searches | History shows |
| Hide related videos | Watch page below player | Related list gone | List shows |

## 7. Navigation bar / Tab bar

- Nav: hide logo, premium logo (worked in r1), notification/search/voice/cast,
  sticky navbar — test the untested ones.
- Tab bar: set **Default tab → You**, relaunch → app opens on the You tab.
  Also test Library on a device that shows the You tab (should pick whichever
  the server sent). Other tabs as before.

## 8. Miscellaneous / Menu items / Appearance / Preferences

- Misc (restart pill on all init-gated): Background playback, upgrade dialogs,
  "Are you there?", snackbar, startup animations, play-next-in-queue,
  like/dislike votes, rate prompts, HUD messages. Plus non-restart: force
  miniplayer (in Player), new miniplayer (moved to A/B).
- Menu items: remove download/watch-later/save-to-playlist/share/not-
  interested/don't-recommend/report.
- Appearance: OLED theme/keyboard (worked r1 — confirm).
- Preferences: export/import/restore/clear cache/auto-clear.

## 9. Beta (unverified — the report loop)

Flip each, test, report "works / broken / n/a" per item:
Hide music shelf, feed posts, subscribe, shop, memberships, clip, remix,
Shorts hide like/dislike/comment/share/remix/products/rec-bar/commit/
subscribe/live/lens/trends/to-video. For anything that works, we move it back
to its proper group; for anything dead, we drop it.

## Report format

```
A/B:    mute=works; chapter=broken (no seek on tap); ...
Watch:  hide like=works both variants; download=broken (still visible)
Beta:   music shelf=broken; shorts like=works
```

Plus the launch log if anything is broken:
`log stream --predicate 'subsystem == "com.nandan.ytfreedom"'`
