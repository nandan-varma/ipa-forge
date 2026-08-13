# YouTube 21.32.4 — safe patch set

Target: `com.google.ios.youtube` v21.32.4 (arm64, thin binaries — no `arch:`
needed). Validated with `forge patch --dry-run` against the real IPA.

## What these patches do (and deliberately don't)

| Patch | Effect | Verified |
| --- | --- | --- |
| `plist_edit` — `CFBundleDisplayName` → "YouTube (patched)" | Visible name under the home-screen icon | dry-run OK |
| `resource_replace` — `90s-video.mp4` | Replaces the signed-out "90 second" preview video with a 2s silent clip (see `assets/`) | dry-run OK |

**What is NOT here, and why:** ad removal and Premium-unlock (background
playback, downloads, PiP) cannot be produced as static patches. YouTube's
binary is string-obfuscated (no plaintext version/vendor strings), the
Premium gating is server-side (the app's `Info.plist` already declares
`UIBackgroundModes: audio`), and ad-suppression requires version-specific
Objective-C swizzling hooks — that's reverse-engineering work (see
`youtube-dylib-inject.yaml` for where a hook dylib would plug in), not a YAML
patch.

## Try it

```bash
forge patch --ipa /Users/nandan/Downloads/com.google.ios.youtube_544007664_21.32.4.ipa \
  --patches patches/youtube-21.32.4/youtube-21.32.4.yaml \
  --identity "Apple Development" \
  --profile <profile authorizing com.google.ios.youtube> \
  --output /tmp/youtube-patched.ipa --dry-run
```

Dry-run first (no `--identity`/`--profile` needed). Drop `--dry-run` and add
your signing inputs for the real run. Note: this app has six app extensions
(AppMigration, Intents, NotificationContent, NotificationService, Share,
WidgetKit) — supply one profile per extension bundle id (or a wildcard
profile) so each embeds a matching profile.

## Files

- `youtube-21.32.4.yaml` — the active patch set above.
- `youtube-dylib-inject.yaml` — dylib-injection template (read its header).
- `assets/90s-video.mp4` — generated replacement resource (produced locally
  with ffmpeg).
