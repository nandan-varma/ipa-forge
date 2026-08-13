# Sources

- **EeveeSpotify** — the maintained open-source Spotify premium-unlock tweak.
  Upstream (`whoeevee/EeveeSpotify`) is DMCA-taken-down; mirrors used:
  `Meeep1/EeveeSpotifyRevivedPublic` and `SideloadLabs/EeveeSpotifyReincarnated`
  (v6.6.7, cloned to `/tmp/eevee3`). Built from source via theos with the
  renamed `EeveeSwiftProtobuf` module (avoids collision with the SwiftProtobuf
  statically embedded in SpotifyShared.framework).
- **zxPluginsInject** (`modules/zxPluginsInject` in the same repo) — sideload
  compat shim: keychain access-group rebind, CloudKit neutering, app-group
  container bridging (equivalent of the YouTube set's SignInFix).
- **SpotC-Plus-Plus** (`SpotCompiled/SpotC-Plus-Plus`) — compiled-IPA repo that
  documents the build pipeline (EeveeSpotify + Sposify).
