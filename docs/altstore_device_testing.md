# Manual AltStore Classic device-test checklist

`forge patch` produces a signed, standard-structure `.ipa`. Everything up to
that point is covered by the automated test suite (`pytest tests/`). What is
**not** and **cannot** be automated in this environment is confirming AltStore
Classic itself accepts, installs, launches, and refreshes the result on a
real iPhone. This is a manual procedure to run by hand.

## Prerequisites

- AltServer running on the same Mac/PC used to sign the IPA, paired with your
  iPhone over USB or Wi-Fi (see AltStore Classic's own setup docs).
- A real (not synthetic) `.ipa` you have legitimate rights to modify, or the
  `fixtures/synthetic_app.ipa` fixture for a structural-only smoke test (it
  will install and its process will launch, but it has no UI).
- A matching `.mobileprovision` and signing identity for your Apple ID's
  team, produced the normal way through AltServer's own account/profile
  management (see the top-level README's certificate/profile section).

## Checklist

1. **Patch**: `forge patch --ipa <input> --patches <patches.yaml> --identity <identity> --profile <profile> --output patched.ipa`
2. **Install**: In AltStore's "My Apps" tab, use "+" and select `patched.ipa`.
   - Expected: install completes without AltStore error 1007 ("not a standard .ipa").
3. **Launch**: Tap the installed app icon on the home screen.
   - Expected: app launches without an "Unable to Install" / "Untrusted
     Developer" prompt (trust the developer certificate in Settings if iOS
     prompts for it on first launch of a personal-team build).
4. **Confirm the patch took effect**: check whatever the patch definition
   changed (a swapped resource, a binary behavior change, etc).
5. **Force a refresh**: in AltStore's "My Apps", pull to refresh (or wait for
   AltServer's background refresh). Confirm the app's expiry date extends
   and the app still launches afterward without re-signing errors.
6. **Expiry note**: a free Apple ID sideload expires after 7 days and AltStore
   currently limits free accounts to 3 active sideloaded apps and 10 App IDs
   per rolling 7-day window -- if refresh silently fails, check those limits
   before assuming the patcher produced a bad IPA.

If any step fails, capture `forge patch --verbose` output (the manifest) and
the on-device error text -- both are needed to tell a patcher bug apart from
an AltStore/account-limit issue.
