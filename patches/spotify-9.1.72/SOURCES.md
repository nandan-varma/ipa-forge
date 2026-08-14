# Sources

This patch set is an original, from-scratch reimplementation. The feature
set and the reverse-engineering targets come from independent analysis of
the Spotify 9.1.72 binary:

- The premium-unlock mechanism was discovered by intercepting Spotify's
  bootstrap and `/v1/customize` responses and analyzing the protobuf wire
  format (field numbers for the account-attribute map, assigned feature
  values, and premium-plan messages were derived from the responses
  themselves and validated with round-trip tests).
- The session-protection targets (`SPTAuthSessionImplementation`,
  `SPTAuthLegacyLoginControllerImplementation`, Ably/URLSession endpoints)
  were identified from the binary's class table and network behavior.
- The HUB ad-component keywords and ad-delivery endpoint list
  (`/ads/*`, DAC, Esperanto slots, sponsored/promoted paths, ad hostnames)
  were catalogued from the binary and from observing what the server sends.
- The sideload keychain/app-group behavior is standard AltStore re-signing
  knowledge (access-group drift, missing app-group entitlements).

The only third-party code vendored is **fishhook** (Facebook, MIT) — and it
is currently **not compiled in** (the v5 crash investigation removed the
SecItem rebind it served; it remains available in the history if a future
sign-in issue needs it).

No external tweak binaries are shipped or injected. Everything is built
from `dylib/*.m` by `dylib/build.sh`.
