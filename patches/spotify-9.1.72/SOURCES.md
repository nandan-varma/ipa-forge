# Sources

- **EeveeSpotify** (whoeevee, DMCA'd; mirrors `Meeep1/EeveeSpotifyRevivedPublic`,
  `SideloadLabs/EeveeSpotifyReincarnated`) — the reference implementation.
  We do NOT ship or inject it (the Swift/Orion build crashes at launch via
  `LC_LOAD_DYLIB`); instead this set reimplements the essential features in
  plain ObjC, using Eevee's *research*:
  - the bootstrap/customize interception targets and the exact protobuf wire
    schema (field numbers for `BootstrapMessage`, `UcsResponse`,
    `ResolveConfiguration`, `AssignedValue`, `AccountAttribute` — from its
    generated SwiftProtobuf models),
  - the account-attribute and assigned-value rule sets (premium attributes,
    ad-flag disabling, capping removal),
  - the session-protection hook targets and blocked endpoint list.
- **zxPluginsInject** (`modules/zxPluginsInject` in the same repos) — the
  sideload compat shim logic (SecItem access-group rebind, app-group
  container, CloudKit neuter) ported to `SideloadFix.m`.
- **fishhook** (Facebook) — C-symbol rebinding for the SecItem wrappers
  (vendored under its MIT license in `dylib/fishhook.{c,h}`).
