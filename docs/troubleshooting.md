# Troubleshooting

Errors are reported as single-line `error:` messages (CLI) or a red banner
(GUI) — never raw tracebacks. This page maps each message to its cause and fix.

## Hook verification reports "missing" / "elsewhere"

**Symptom:** `forge patch --dry-run` or `forge hooks verify` reports a hook
with `missing-class`, `missing-selector`, or `elsewhere`. A
`referenced-only` status means the selector is referenced by the binary but
not declared as a method anywhere — there is no IMP to swizzle, so the hook
cannot attach no matter what class you point it at (double-check with
`forge hooks find <selector> --ipa App.ipa` before porting it).

**Cause:** the app version doesn't have the class/selector the tweak targets —
a silent no-op on device (feature stops working, no crash). This is exactly
what the `hooks:` block exists to catch.

**Fix:** find the new name: `forge hooks extract --ipa App.ipa --search
"<substring of old class>"` shows what replaced it (e.g. `YTWatchBreakController`
→ `YTAdsControlFlowManagerImpl`). Update the hook target (and the tweak
source), then re-run `--dry-run`. Statuses `unverified` and `ok-inherited`
are soft — the class/selector likely exists but the parser couldn't fully
confirm (system superclasses, chained-fixup gaps) — verify once on device
via your tweak's attach logs rather than chasing them.

## Patch definition problems

### `patch definition '<file>' is invalid: ...`

The YAML parsed but failed schema validation (missing `target`, unknown
`type`, missing required field, empty `patches:` list, `plist_edit` `set`
without a `value`, etc.). The message names the failing field(s). Fix the
definition per the [Patch Definition Reference](patch-reference.md).

### `patch definition '<file>' is not valid YAML: ...`

The file isn't parseable YAML — check quoting/indentation. (YAML and JSON are
both accepted.)

### `patch definition '<file>' matches 0 patch operations for <bundle> v<version> (definition targets <other>); nothing will be applied`

The `target` block doesn't match this IPA. Check `bundle_id` (typo?) and the
`version` rule (`exact` is string equality — `"1.0.0"` won't match
`"1.0.0-beta"`; `max` is exclusive).

- In `--dry-run` this is a **warning** (handy for confirming a version gate).
- In a real run it's a hard error: `refusing to produce an unpatched IPA`.

### `patch dry-run validation failed: <op_id>: <message>`

The dry-run gate rejected the patch — nothing was modified. Common causes:

| Message | Cause / fix |
| --- | --- |
| `expected N match(es), found M at offsets [...]` | `binary_replace`: the pattern occurs M times. Set `expected_matches` to M, or fix the pattern |
| `replacement length (N) must equal pattern length (M)` | Count the hex tokens — they must match, wildcards included in `pattern` only |
| `invalid hex byte token '<tok>'` / `byte token '<tok>' out of range` | `pattern`/`replacement` must be space-separated hex (`00`-`ff`) plus `??` |
| `executable '<name>' not found in bundle inventory` | The `executable` basename doesn't match any Mach-O in the bundle — run `forge inspect` to see the real names |
| `<path> is not a valid Mach-O file` | The targeted executable isn't a parseable Mach-O |
| `<path> is a universal binary ... an explicit arch: selector is required` | Fat binary — add `arch:` (`arm64`, `armv7`, `x86_64`, `i386`) |
| `Architecture '<arch>' not found in <path>` | Wrong `arch:` — the message lists available ones |
| `source '<path>' does not exist` | The `source:` file isn't where expected — it resolves relative to the **definition file's directory** |
| `destination '<dest>' does not exist (use resource_add to create new files)` | `resource_replace` on a missing path → switch to `resource_add` |
| `destination '<dest>' already exists (use resource_replace to overwrite)` | `resource_add` on an existing path → switch to `resource_replace` |
| `destination '<dest>' is not a file (only files can be removed)` | `resource_remove` on a directory — only files can be removed |
| `destination '<path>' escapes the app bundle root` | `path:` must stay inside `Payload/<App>.app/` — `../` is rejected |
| `key '<key>' not present in <plist>` | `plist_edit` `remove` on a key that isn't there |
| `plist_edit with action 'set' requires a non-null 'value'` | Provide a `value` for `set` (null isn't allowed) |
| `unknown load_command '<cmd>'` / `INJECTION_FAILED: ...` | `dylib_inject` — use `LC_LOAD_DYLIB` or `LC_LOAD_WEAK_DYLIB`; check the arch; see below |

### Dylib injection specifics

- `INJECTION_SKIPPED: <name> is already loaded` — the load command already
  exists; the operation is a no-op (not an error).
- `INJECTION_UNSUPPORTED: ... is not a valid Mach-O file` — wrong
  `executable`.
- Remember `dylib_inject` only adds the load command — the dylib file must
  already be in the bundle (pair it with a `resource_add`). An injected but
  unstaged dylib passes the pipeline but fails at runtime on device.

## Signing problems

### `no codesigning identity matches '<query>'` / `'<query>' matches multiple ...`

The `--identity` substring doesn't uniquely match anything in
`security find-identity -v -p codesigning`. Use the full SHA-1, a more
specific substring, or a valid name.

### `provisioning profile '<name>' (<uuid>) expired on <date>`

The profile is expired — obtain a fresh one (Xcode or AltServer's pairing).

### `provisioning profile '<name>' authorizes '<pattern>', not '<bundle_id>'`

The profile's `application-identifier` (team prefix stripped) doesn't cover
this bundle id. Use a matching profile, or a wildcard (`TEAMID.*`) profile.

### `no supplied provisioning profile authorizes bundle id '<id>' (available: ...)`

Multiple profiles supplied, none of them match this target's bundle id.
Supply a matching `--profile` for it.

### `multiple supplied profiles authorize '<id>': ...` / `multiple supplied wildcard profiles: ...`

Two profiles claim the same bundle id (or two wildcards) — remove the
duplicate so selection is unambiguous.

### `profile '<name>' does not authorize '<bundle_id>' but will be embedded anyway (single-profile mode)`

Warning only: one profile is signing everything, including an extension it
doesn't authorize. Install may fail on device — supply a matching profile for
that extension.

### `codesign failed for <target>: ...` / `codesign verification failed for <target>: ...`

The signing stage failed. Common causes: expired identity, revoked
certificate, entitlements the profile doesn't authorize, or a corrupted
extraction. Check the `codesign` stderr in the message.

## CLI / environment

### `error: --identity is required unless --dry-run is set` / `error: at least one --profile is required unless --dry-run is set`

A real (non-dry-run) patch needs both. Add them, or add `--dry-run` to only
validate.

### `<path> is not a valid zip archive` / `IPA does not contain a Payload/ directory` / `Expected exactly one Payload/*.app, found N`

The input isn't a standard-structure IPA. ipa-forge requires exactly one
`Payload/<App>.app` — re-export from Xcode or re-download the IPA.

## GUI problems

- **`identity is required unless dry_run is set` / `at least one provisioning
  profile is required unless dry_run is set` (400)** — uncheck "Dry run only"
  and fill the signing fields, or tick it to validate without signing.
- **Zip upload errors** — the zip must contain exactly **one** top-level
  `.yaml`/`.yml`/`.json`; entries escaping the extraction directory are
  rejected (zip-slip guard); oversized archives are refused.
- **Download link missing** — dry runs produce no artifact, so there is no
  download button.
- The GUI binds `127.0.0.1` only. If `forge gui` fails to start with
  "address already in use", another instance (or an older build) is on that
  port — stop it or pass `--port`.

## Debugging tips

1. `forge inspect <ipa>` — confirm bundle id/version and executable names
   before writing a definition.
2. `forge patch ... --dry-run --verbose` — the manifest shows every operation's
   status and message without touching anything.
3. Read the manifest's `patches_applied` — each entry carries the operation's
   own message (e.g. match offsets).
4. Check `security find-identity -v -p codesigning` and
   `security cms -D -i <profile>` to confirm the signing inputs themselves.
5. For device-install failures, follow the manual checklist in
   [`docs/altstore_device_testing.md`](altstore_device_testing.md).

## Related

- [`usage.md`](usage.md) — CLI
- [`patch-reference.md`](patch-reference.md) — the YAML contract
- [`adding-an-app.md`](adding-an-app.md) — porting
- [`README.md`](README.md) — docs index
