# SpotifyMod v0.0.9 — device test sheet

Install `/Users/nandan/dev/ytlite-ipa/SpotifyMod_v0.0.9.ipa` (unsigned — AltStore
re-signs on install). Confirm build: Settings → **SpotifyMod** → About section →
version row = **SpotifyMod v0.0.9**.

Base: `com.spotify.client` 9.1.72 (build 917201896, decrypted).
Audit before this build: 20/21 hooks attach (`NSFileManager
containerURLForSecurityApplicationGroupIdentifier:` is a system class — expected),
0 required hooks failing, no old-tweak references in the dylib.

## What changed in v0.0.9

- **Spread re-asserted after EVERY item repositioning**: the element's own
  `layoutSubviews` is hooked — it fires after the app moves an item by any
  mechanism (manual frames, constraints, or collection layout), so the
  spread is re-applied right after and the app can never win the layout
  fight. The re-assert is idempotent (only differing frames are written), so
  it converges instead of looping.
- **Hidden slots handled in the in-layout pass**: hidden plain-view elements
  are zero-widthed (not just skipped) when no removal is allowed.
- **Runtime hierarchy dump**: ~2s after launch the log records the tab bar's
  actual view tree (classes, frames, ids, labels). If spacing is still off,
  that dump tells us exactly what the bar is made of.

## What changed in v0.0.8

- **One toggle instead of two**: the separate "Hide Premium tab" / "Hide
  Create tab" switches are consolidated into a single **Hide Premium &
  Create tabs** switch (Interface section). Both tabs are always hidden
  together — no more intermittent "one works, one doesn't" (old two-toggle
  state is migrated automatically).
- **Spacing made deterministic**: the collection view re-positions cells on
  every layout pass, which could undo the spread. v0.0.8 now re-applies the
  spread (visible tabs = equal widths across the full bar, hidden cells =
  zero-width) inside the collection view's own `layoutSubviews`, right after
  it runs — the app's layout can never win. Removal still only happens from
  safe contexts; the in-layout pass is spread-only.
- **Hidden-cell bug fixed**: hidden cells are now zero-widthed and parked off
  the right edge (previously they kept their old slot frame and could sit on
  top of a visible tab).

## What changed in v0.0.7

Ground truth for this pass comes from the 9.1.72 binary's method tables,
not guesses:

- **The bar is a UICollectionView** (Encore `TabsView`) holding one
  `TabItemCell` per tab, each containing a `TabBarItemElementView`. Removing
  the element empties its cell but the **cell keeps its slot** — that was
  the "empty space" all along. The layout never re-flows on its own
  (regular/compact views have no `layoutSubviews` override).
- **Create detection restored**: v0.0.5 dropped the identifier + CreateTabView
  signals that v0.0.4 used, leaving only a class check that doesn't match —
  that's why create stopped hiding. v0.0.7 detects Create from the element
  **or its cell** id/label containing "create"/"creation", or the element
  containing CreateMenuTabBarItemView/CreateTabView. Premium uses
  "premium" id/label. Both evaluated independently.
- **Spacing fixed by scanning the BAR ROOT**: earlier builds scanned the
  element's own parent (one slot per scan → nothing could ever spread).
  v0.0.7 finds the bar root (the collection view) and spreads its cells
  evenly, zero-widthing the hidden cells. Re-applied every second for 20s
  after launch so the app's own layout can't win between passes.

## What changed in v0.0.6

- **Launch crash fixed**: v0.0.5 crashed because one `static` original-IMP slot
  was shared across three `layoutSubviews` hooks (TabBarRegularView,
  TabBarCompactView, Encore TabsView) — after the last hook installed, every
  layout hook called the *wrong class's* layoutSubviews with a mismatched
  self. All `layoutSubviews` hooks are removed (they were never essential):
  the fix now runs only from safe triggers — `setViewControllers:` (VC
  filter), `viewDidLayoutSubviews` (post-layout), element install (async),
  and delayed self-heal. Every hook body is also wrapped in `@try` so a
  layout hiccup logs instead of crashing.
- **Same latent bug fixed in the premium patch**: `hookURLSessionDelegate`
  shared one static original-IMP across its two hook classes — now per-class
  `__block` originals.
- Behavior (detection + cell spreading) is unchanged from v0.0.5.

## What changed in v0.0.5

- **Premium-only now works**: the premium element was being misclassified as
  Create (a `!isCreate` gate blocked it unless Create hiding was also on).
  Detection is now precise and evaluated independently:
  - Create = element contains `CreateMenuTabBarItemView`
  - Premium = `tabbar-item-*` id contains "premium" or a "Premium" label
  - the CreateTabView / "create"-identifier heuristics that cross-matched
    the premium element are removed
- **Space now fills**: the tabs live one-per-cell in a collection view, so
  spreading *elements* did nothing (each parent had exactly one). v0.0.5
  spreads the **cells** evenly across the bar and zero-widths the hidden
  cells, then re-applies from every layout trigger so the app's own layout
  can't win between passes.
- Detection logging added: every element match is logged (see below).

## What changed in v0.0.4

- **Root cause of v0.0.3 (both tabs visible) found**: the tab bar container
  (`NavigationUI_TabBarImpl.TabBarContainer`) is a **UIViewController**, not a
  UIView. v0.0.3 hooked its `layoutSubviews` (which doesn't exist on a VC —
  the hook installed nothing) and looked for the container while walking the
  *view* chain (a VC is never there — every scan found nothing). v0.0.2 only
  worked because it scanned the element's direct parent.
- **New data-level fix**: `setViewControllers:` is hooked and the Premium
  (`PDPViewController`) / Create (`CreateMenuViewController`) view controllers
  are dropped from the array **before** the tab items are built — the bar
  renders only the remaining tabs, natively spaced (no gap possible).
- **Redundant view-level fix kept**: any hidden element view that still
  appears (built before the filter ran) is removed, and the surviving
  elements are spread evenly across the bar.
- Triggered from `viewDidLayoutSubviews` (the VC's real layout method) +
  element install + delayed self-heal re-scans.

## What changed in v0.0.3

- **Tab hiding rework (fixing the two reported bugs)**:
  - **Space now fills**: hidden tabs are removed AND the remaining tab
    elements are redistributed into equal-width slots across the bar on
    every layout pass (v0.0.2 left a hole — the bar laid out at fixed slots).
  - **Create hiding fixed**: the Create content view class is now hooked
    directly (it could install after the first scan), detection falls back
    to the `tabbar-item-*` accessibility identifier ("create"/"creation"),
    and a self-heal re-scan runs every 2s for 12s after launch so late
    items get removed too.

## What changed in v0.0.2

- **New: hide bottom-bar tabs** — Interface section with two opt-in toggles:
  **Hide Premium tab** and **Hide Create tab** (both OFF by default). Hooking
  the Swift tab bar (NavigationUI_TabBarImpl): hidden tab element views are
  removed and the bar re-lays out the survivors. All 3 new tab hooks
  verified attaching to the 9.1.72 binary.

## What changed in v0.0.1

- **Full audit vs the 9.1.72 IPA**: every hook target verified against the main
  binary + SpotifyShared.framework. Nothing targets an old tweak.
- **Settings rebuilt from a single source of truth** — the feature catalog in
  `dylib/SpotifyFeatures.m` (one row per setting: key, title, detail, group,
  kind, default, restart). Defaults register from it, the screen renders from it,
  the restart hints come from it. Adding/removing a feature = one catalog row.
- **Settings screen reorganized** — Essentials (top): Premium unlock, Ad blocker,
  Session protection. Advanced (bottom): App-group fix + **Ad blocking strength**
  dropdown (Standard / Aggressive). Future: greyed-out roadmap rows (do nothing).
  About: version, reset-all, relaunch note.
- **Not-everything-is-a-toggle**: Ad blocking strength is now a dropdown
  (checkmark picker), not a switch.
- **Toggle ownership fixed**: network-level ad blocking now follows the **Ad
  blocker** toggle (was lumped under Session protection). At defaults nothing
  changed — Aggressive = exactly the old behavior.
- **Restart hints**: flipping any setting shows a "Restart to apply" pill
  (all settings are read at launch).
- **Reset all settings** row in About (clears every SpotifyMod key).

## 0. Smoke (1 min)

1. Launch — no crash. Settings → SpotifyMod row visible at the top of Spotify's
   settings list, opens the mod screen.
2. Screen shows 5 sections in order: **Essentials, Interface, Advanced, Future,
   About**.
3. Essentials: 3 switches, all ON. Interface: 2 switches, both **OFF**.
   Advanced: 1 switch ON + "Ad blocking strength" row showing **Aggressive**.
   Future: 4 greyed-out rows, taps do nothing. About: version row, Reset row,
   relaunch note.
4. Flip Premium unlock OFF → "Restart to apply" pill appears. Flip back ON.
5. Ad blocking strength → tap → checkmark picker with Standard/Aggressive;
   current selection checked. Pick Standard, pop back, row shows "Standard".

## 1. Always-on (no toggle)

- Sign-in: log in with your free account, survives relaunch.
- **Premium unlock** (Essentials ON): no forced-logout, no shuffle-lock —
  play any song on demand, skip freely.
- **Ads** (Essentials ON, strength Aggressive): play 3 songs + browse Home +
  search → zero audio/video/banner ads.

## 2. Essentials (curated — the defaults you chose)

| Item | Test | Works = | Broken = |
| --- | --- | --- | --- |
| Premium unlock | Free account, play on demand | Any song plays, no shuffle-lock | Shuffle-locked / can't play |
| Ad blocker | Play + browse + search | No ad cards, no audio ads | Ads still appear |
| Session protection | Use app 5+ min, switch accounts in another session | No forced logout | Kicked to login |

## 2b. Interface (single toggle — OFF by default)

1. Settings → Interface → enable **Hide Premium & Create tabs** (restart
   pill shows) → relaunch.
2. Bottom bar shows **Home · Search · Your Library** only — Premium and the
   Create (+) button are gone, **evenly spaced across the full bar width**
   (no hole, no dead zone).
3. Switch tabs (Home → Search → Library) — all still work after hiding.
4. Rotate to landscape and back — the bar stays evenly spaced.
5. Turn the toggle OFF → relaunch → both tabs are back at their original
   spacing.

> The Premium tab only exists for free accounts; if you're signed in with a
> premium-ish state the Premium tab may not render at all, report Premium as
> N/A and confirm Create alone hides + re-spaces.

### If a tab still shows, grab the launch log

```bash
log stream --predicate 'subsystem == "com.nandan.spotifymod"'
```

Then relaunch and report which of these lines appear:

- `hooked -[TabBarContainer setViewControllers:]` / `viewDidLayoutSubviews` —
  hooks installed (missing = hook install failed)
- `filtering tab VC <class>` — the VC filter dropped a tab
- `tab detect <class>: create=X premium=X hidden=X id=<id>` — per-element
  classification (tells us exactly why a tab was or wasn't hidden)
- `hiding tab <x>` — the element was removed
- `tab layout: N visible of M slots in <class>` — redistribution ran
- `--- tab bar hierarchy dump ---` / `[0]..[n]` / `bar ... children=...` —
  the runtime view tree (classes + frames + ids). **If spacing is still
  off, send these lines** — they name the real container and slot views.

## 3. Advanced (power user)

- **App-group fix** — OFF: relaunch, confirm the app still launches and stays
  signed in (the fix is defensive; behavior should be identical on this build —
  report if turning it off breaks anything).
- **Ad blocking strength**
  - **Standard**: play + browse → no ads; keep using the app for 2+ min —
    confirm nothing breaks when bootstrap/customize re-fetch is NOT blocked.
  - **Aggressive** (default): as Standard, plus free-tier re-fetch suppression.

## 4. Future (disabled by design)

Downloads unlock, Audio quality selector, Startup tab, Settings import/export —
greyed out, do nothing on tap. If any of them does something, that's a bug.

## 5. About

- Version row reads **SpotifyMod v0.0.1**.
- **Reset all settings** → confirm → pill appears → relaunch → all switches back
  ON, strength back to Aggressive.

## Report format

```
Essentials: premium works (no shuffle-lock); ads blocked everywhere tested; no forced logout
Advanced: standard mode OK, aggressive OK; app-group off harmless
Settings UI: sections/order correct; picker checkmark moves; restart pill shows
```

Plus the launch log if something is broken:
`log stream --predicate 'subsystem == "com.nandan.spotifymod"'`
Watch for `hooked -[...]` at launch, `patched bootstrap/customize`,
`cancelled ad|refetch <url>`, `blocked logout <url>`.
