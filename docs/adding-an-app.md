# Adding a new app — end-to-end playbook

This is the canonical "give me an IPA, port everything" procedure. It is
generic; the per-app runbooks ([YouTube](../patches/youtube/PLAYBOOK.md),
[Spotify](../patches/spotify/PLAYBOOK.md)) apply it to their apps.

## Phase 0 — accept the IPA

- Confirm the input is **decrypted** (an App-Store-shaped IPA with the same
  name + numeric suffix is usually DRM-encrypted; the binary will fail to
  run even though forge can dry-run it).
- `forge inspect <ipa>.ipa` — bundle id, version, main executable, embedded
  extensions/frameworks. Record them.
- `forge hooks extract --ipa <ipa>.ipa --class <MainClass>` — sanity-check
  that the binary parses (mergeable/zero-based dylibs and frameworks are
  handled; see `architecture.md`). If you already have an extracted bundle,
  pass `--app-dir Payload/<App>.app` instead of the IPA to skip
  re-extraction — every `forge hooks` command accepts it.

## Phase 1 — create the patch set

```
patches/<app>-<version>/
  <app>-mod.yaml      # the definition: ops + hooks: block
  dylib/              # the hook dylib sources + build.sh
  PLAYBOOK.md         # this app's runbook (copy the template below)
  README.md           # features, build, apply, verify
  SOURCES.md          # attribution / research lineage
```

The definition's shape is always:

```yaml
target: { bundle_id: "...", version: { exact: "..." } }
patches:
  - resource_remove:  # AltStore appends the Team ID to the main bundle id at
                      # install, breaking embedded extension/watch ids
                      # (IXErrorDomain Code=2) — strip them, same as the
                      # YouTube/Spotify sets
  - resource_add:     # stage the hook dylib into Frameworks/
  - dylib_inject:     # LC_LOAD_WEAK_DYLIB (weak — a load failure degrades
                      # instead of aborting; the community-proven load model)
hooks: [ ... ]        # every hook the dylib relies on (see below)
```

## Phase 2 — build the hook dylib (plain ObjC)

- **Plain ObjC-runtime swizzling only.** No Swift, no substrate, no external
  frameworks beyond Foundation/UIKit/Security. The two reference dylibs
  (`patches/*/dylib/`) are the templates; copy the plumbing
  (`<prefix>Hook.h`: `hookInstance`/`hookClass` inline helpers + os_log).
- **The constructor is inert**: it only schedules the real install on the
  main run loop (`dispatch_async(dispatch_get_main_queue())`). Hooks install
  after launch, when every image is loaded — the substrate-style late-load
  model that sidesteps the whole class of load-time crashes.
- **Every feature init is `@try`-isolated** (`safeInit(name, block)`): a
  failure logs and degrades; it can never take the app down.
- One file per feature area, one hook per method across the dylib (shared
  surfaces are owned by a single file — a second hook on the same method
  silently replaces the first).
- The dylib's `build.sh` stages `build/<Name>Hook.dylib` for the definition.

## Phase 3 — declare + verify hooks

- Declare every hook target in the definition's `hooks:` block:

```yaml
hooks:
  - class: "SomeClass"
    selector: "someMethod:"
    required: true          # fail the run if this one can't attach
  - class: "SomeOther"
    selector: "addedThing"
    added: true             # the tweak adds it (logos' %new)
```

- Generate the block from sources when possible:
  `forge hooks manifest --dir dylib/ --required hooks-required.txt`
  (recognizes direct `NSClassFromString` + variable-resolved calls, and
  class names passed through a local resolver helper like
  `igClass("X")` — any function whose body calls `NSClassFromString`;
  helper/loop-based hooks where the class flows through *another* function
  are declared manually).
- `forge patch --dry-run` verifies every hook against the **main binary and
  all embedded frameworks** (`analyze_bundle`) and fails on missing
  `required` hooks. Statuses: `ok` / `ok-inherited` / `ok-system` / `added`
  / `unverified` (soft) / `missing-class` / `missing-selector` / `elsewhere`
  (hard). A class/selector the walk missed but that is still present as a
  string in the binary reports `unverified` with a "string present … walk
  missed it" hint — no more manual `strings <binary> | grep` cross-check.
  The parser under-reports GPBMessage methods.
- Porting later: `forge hooks diff --old prev.ipa --new next.ipa --patches Y`
  shows exactly which hooks regressed.

## Phase 4 — build + device loop

```bash
patches/<app>-<version>/dylib/build.sh
forge patch --ipa <base>.ipa --patches patches/<app>-<version>/<app>-mod.yaml \
  --output /tmp/x.ipa --dry-run     # hooks gate must pass
forge patch --ipa <base>.ipa --patches patches/<app>-<version>/<app>-mod.yaml \
  --no-sign --output /Users/nandan/dev/ytlite-ipa/<App>Mod_<version>_unsigned.ipa
```

- User sideloads via AltStore → report. Device logs are the deduction tool:
  give the dylib a unique os_log subsystem (`<prefix>Log`), log every hook
  attach at install, and every feature's `ready`/`disabled` state.
- **If it crashes at launch**: build a do-nothing test dylib
  (constructor os_log only, weak LC, same strip ops) and inject it. If the
  test launches, the crash is in your hook code — bisect features
  (drop the riskiest first: any C-level rebinding like fishhook, then
  per-feature). If the test also crashes, the problem is the injection /
  signing / stripping itself, not the dylib.

## Phase 5 — ship the docs

- Copy the runbook template from an existing `PLAYBOOK.md`; fill in the
  app-specific commands, hook verification results, and debugging log
  subsystem.
- Write `README.md` (features, build, apply, verified-on table) and
  `SOURCES.md` (attribution; keep it original-work, no external team names
  unless they ask).
- Link the new patch set from [`docs/README.md`](README.md).

## Templates

The dylib plumbing, the `build.sh`, and the definition YAML in the two
existing patch sets are the living templates — copy them, don't reinvent.
`forge hooks manifest` and `forge hooks diff` keep the hooks surface honest
as the app updates.

## Related

- [`adding-a-feature.md`](adding-a-feature.md) — per-feature conventions
- [`patch-reference.md`](patch-reference.md) — the YAML contract
- [`usage.md`](usage.md) — CLI
- [`README.md`](README.md) — docs index
