# YouTube Pro v0.0.7 — device test sheet

Install `/Users/nandan/dev/ytlite-ipa/Youtube_pro_v0.0.7.ipa`. Confirm build:
Settings → YTFreedom → version row = **v0.6.2**.

## What changed in v0.0.7

- **SponsorBlock** (new, from iSponsorBlock reference): auto-skips sponsor
  segments. Toggle: Advanced → System → SponsorBlock (default OFF — it sends
  video IDs to api.sponsor.ajay.app). When on: fetches segments for the
  current video and seeks past them (1s poll; no player-bar UI yet).
- **Keep screen on** (new, DEMC-style): prevents auto-lock/dimming while a
  video is playing. Advanced → System → Keep screen on.
- **Quality + speed moved to Beta**: Old quality picker and Extra speeds are
  version-gated by the app on 21.32.4 and could not be made to work; their
  toggles now live in Advanced → Beta (marked beta, default OFF). Their
  hooks stay installed so they can be flipped for experiments, but treat them
  as non-functional.
- RYD (dislike counts) stays deferred: its watch-page hook target
  (updateLikeButtonWithRenderer:) is absent in 21.32.4.

## 0. Smoke
## 0. Smoke
## 0. Smoke
## 0. Smoke
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
