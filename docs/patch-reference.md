# Patch Definition Reference

This is the complete reference for writing patch definition files for ipa-forge.
A patch definition is a single YAML (or JSON) file that describes *what* to
change in an app bundle, keyed by bundle id + version. ipa-forge never embeds
app-specific logic — everything it does to an app comes from files like this.

Working examples live in [`fixtures/patches/`](../fixtures/patches/):

- `example.yaml` — `binary_replace` + `resource_replace`
- `example_dylib_inject.yaml` — `dylib_inject`
- `example_plist_edit.yaml` — `plist_edit`

## File structure

```yaml
target:            # which app this definition applies to (required)
  bundle_id: "com.example.app"
  version: { exact: "1.2.3" }     # or { min: "1.0.0", max: "2.0.0" }

patches:           # one or more operations (required, non-empty)
  - id: "my-op-1"                 # arbitrary unique id, shown in output
    type: binary_replace          # one of the types below
    # ... type-specific fields ...
```

Definitions are loaded with `yaml.safe_load` (no arbitrary code execution) and
validated against a pydantic schema; a file that fails validation produces a
single-line actionable error, never a traceback. An **empty `patches:` list is
rejected** — a definition with no operations is always a mistake.

## The `target` block — matching

The definition only applies when *both* conditions hold:

| Field | Meaning | Matching rule |
| --- | --- | --- |
| `bundle_id` | `CFBundleIdentifier` of the app | exact string equality |
| `version` | `CFBundleShortVersionString` of the app | see below |

### Version matching

Two forms, mutually exclusive:

```yaml
version: { exact: "1.2.3" }          # string equality against the bundle's version
version: { min: "1.0.0", max: "2.0.0" }   # numeric range
```

- `exact` compares the raw strings: `exact: "1.0.0"` will **not** match a bundle
  whose version is `1.0.0-beta`.
- `min`/`max` compare numerically. **`max` is exclusive** — `max: "2.0.0"` matches
  `1.9.9` and `1.5.0-beta` but not `2.0.0`.
- Range matching strips non-numeric segments, so `1.0.0-beta` and `1.0.0` are
  considered equal for `min`/`max` purposes.
- Both `min` and `max` are optional; `{min: "1.0.0"}` means "1.0.0 or later".

### What happens when the target does not match

If the supplied definition's `target` does not match the IPA you patched, zero
operations resolve:

- `forge patch --dry-run` **warns** ("matches 0 patch operations ... nothing
  will be applied") and still succeeds — useful for confirming a version gate.
- a real (non-dry-run) `forge patch` **fails** with
  "refusing to produce an unpatched IPA". A typo'd bundle id can never silently
  produce an unpatched output.

## Common fields

| Field | Required | Meaning |
| --- | --- | --- |
| `id` | yes | Unique identifier for the operation; reported in the manifest and error messages |
| `type` | yes | Discriminates the operation type (below) |

## Operation types

### `binary_replace` — deterministic byte patching

Replaces an exact byte sequence inside a Mach-O executable with a fixed
replacement.

```yaml
- id: "zero-marker-bytes"
  type: binary_replace
  executable: "TestApp"        # basename of the Mach-O file inside the bundle
  arch: "arm64"                # required for fat/universal binaries
  pattern: "ca fe f0 0d de ad" # space-separated hex bytes
  replacement: "00 00 00 00 00 00"
  expected_matches: 1          # optional, default 1
```

| Field | Required | Meaning |
| --- | --- | --- |
| `executable` | yes | Basename of the target Mach-O (main executable, a framework's binary, a dylib) as found by the inventory walker |
| `pattern` | yes | Space-separated hex bytes; `??` is a single wildcard byte (`ca fe ?? 0d` matches any byte in that position) |
| `replacement` | yes | Same number of tokens as `pattern`; **no wildcards allowed** and the length must match exactly |
| `expected_matches` | no | Number of matches required for success (default `1`). Fails loudly on any other count (0 = pattern not present; >1 = ambiguous) |
| `arch` | no | Architecture slice to search (see below) |

Semantics:

- The search is **bounded to one architecture slice**: for a fat/universal
  binary the pattern is only matched within the selected slice's byte range, so
  a patch can never silently land in the wrong architecture. For thin binaries
  the whole file is searched and `arch` is unnecessary.
- A universal binary **without** `arch` is an error ("an explicit `arch:` selector
  is required") — ipa-forge refuses to guess.
- Supported arch names: `arm64`, `armv7`, `x86_64`, `i386`.
- If the pattern occurs more than once, every occurrence is replaced (and
  `expected_matches` must match the actual count).
- The operation fails during **dry run** if: the executable isn't in the bundle,
  the pattern is malformed, the file isn't Mach-O, or the match count differs.

### `resource_replace` — overwrite a bundle file

```yaml
- id: "swap-asset"
  type: resource_replace
  path: "asset.txt"                       # bundle-relative destination
  source: "assets/patched_asset.txt"      # relative to the definition file
```

| Field | Required | Meaning |
| --- | --- | --- |
| `path` | yes | Bundle-relative destination path (inside `Payload/<App>.app/`). Must already exist as a file |
| `source` | yes | Path to the replacement file, **relative to the definition file's own directory** |

- `source` may also be an absolute path or `../` reference — the definition,
  the IPA, and the signing credentials are all supplied by the same trusted
  user, so sources are intentionally not sandboxed.
- Fails in dry run if the source is missing or the destination doesn't exist
  (use `resource_add` to create new files instead).

### `resource_add` — add a new bundle file

```yaml
- id: "add-hook-lib"
  type: resource_add
  path: "Frameworks/libHook.dylib"
  source: "assets/libHook.dylib"
```

- Identical fields to `resource_replace`.
- Creates intermediate directories as needed.
- Fails in dry run if the destination already exists (use `resource_replace`
  to overwrite) or the source is missing.

### `resource_remove` — delete a bundle file

```yaml
- id: "remove-obsolete-asset"
  type: resource_remove
  path: "obsolete.txt"
```

| Field | Required | Meaning |
|---|---|---|
| `path` | yes | Bundle-relative file or directory to remove. Directories are removed recursively |

- Fails in dry run if the destination doesn't exist or is a directory.

### `dylib_inject` — add a dylib load command

Adds an `LC_LOAD_DYLIB` (or `LC_LOAD_WEAK_DYLIB`) entry to a Mach-O so the
runtime loads the named dylib.

```yaml
- id: "inject-hook"
  type: dylib_inject
  executable: "TestApp"
  arch: "arm64"                     # required for fat/universal binaries
  install_name: "@rpath/libHook.dylib"   # the load path, not a source file
  load_command: "LC_LOAD_DYLIB"     # optional; or LC_LOAD_WEAK_DYLIB
```

| Field | Required | Meaning |
| --- | --- | --- |
| `executable` | yes | Basename of the Mach-O to modify |
| `install_name` | yes | The exact load path added to the binary (e.g. `@rpath/libHook.dylib`) |
| `arch` | no | Architecture slice; required for fat/universal binaries |
| `load_command` | no | `LC_LOAD_DYLIB` (default) or `LC_LOAD_WEAK_DYLIB` |

Critical pairing — **this operation does not copy the dylib into the bundle.**
The dylib file must already be present (shipped with the app, or placed there
with a `resource_add`). The standard pattern is:

```yaml
patches:
  - id: "stage-dylib"
    type: resource_add
    path: "Frameworks/libHook.dylib"
    source: "assets/libHook.dylib"
  - id: "link-dylib"
    type: dylib_inject
    executable: "TestApp"
    install_name: "@rpath/libHook.dylib"
```

Outcomes (reported per-operation in the manifest):

| Status | Meaning |
| --- | --- |
| `INJECTED` | Load command added |
| `INJECTION_SKIPPED` | The dylib is already loaded — no change needed (idempotent) |
| `INJECTION_UNSUPPORTED` | Target is not a parseable Mach-O |
| `INJECTION_FAILED` | Ambiguous/missing arch, unknown load_command, or LIEF failed |

Dylib injection is deliberately the **most fragile** operation — it rewrites
Mach-O load commands and forces a full re-sign. Prefer `binary_replace` or
resource operations when they can express the change.

### `plist_edit` — set/remove Info.plist keys

```yaml
- id: "set-display-name"
  type: plist_edit
  action: "set"            # or "remove"
  key: "CFBundleDisplayName"
  value: "Patched App"     # required when action is set
  path: "Info.plist"       # optional, bundle-relative, defaults to Info.plist
```

| Field | Required | Meaning |
| --- | --- | --- |
| `action` | yes | `set` (create or overwrite the key) or `remove` (delete it) |
| `key` | yes | The plist key |
| `value` | only for `set` | Any plist value (string, number, boolean, list, mapping) — a `set` with a null value is rejected |
| `path` | no | Bundle-relative plist path; defaults to the app's `Info.plist` |

- `remove` fails in dry run if the key is not present.
- Works on binary or XML plists transparently.

## How operations run: the dry-run gate and ordering

`forge patch` never mutates anything until **every** operation has reported
`dry_run_ok` (the "dry-run gate"). If any operation would fail, the whole patch
is rejected before a single file changes.

When applying, operations run in a fixed order:

1. Resource operations (`resource_replace`/`resource_add`/`resource_remove`)
   and `plist_edit` — they don't touch Mach-O layout.
2. `binary_replace` — raw byte edits.
3. `dylib_inject` — **last**, because LIEF's load-command rewrites can shift
   byte offsets that binary patches depend on.

Order within a group follows the order in the YAML file.


## The `hooks` block — verify runtime hooks against the binary

Dylib-injection tweaks live or die on ObjC runtime hooks: the dylib swizzles
`-[Class selector]`, and when a **newer app version renames or removes that
class/selector the hook silently no-ops** — the feature just stops working
with no error. The `hooks:` block declares every hook the patch set relies on
so `forge` can verify it against the actual binary before anything mutates:

```yaml
hooks:
  - class: "YTColdConfig"
    selector: "iosEnableMuteButtonPlayerControl"
    kind: instance        # instance (default) | class
  - class: "YTPlayerResponse"
    selector: "playerAdsArray"
    added: true           # the tweak ADDS this method (logos' %new)
  - class: "SSORPCService"
    selector: "URLFromURL:withAdditionalFragmentParameters:"
    required: true        # fail the run if this hook can't attach
```

Per hook:

| Field | Meaning |
| --- | --- |
| `class` | ObjC class name the hook targets. |
| `selector` | Selector, colons included (`didReceiveAdBreakResponse:fromAdBreakSlot:`). |
| `kind` | `instance` (default) or `class` (metaclass method). |
| `added` | The tweak adds the method itself (`%new`). Absence is *expected* and counts as a pass; if the binary's selrefs reference the selector, the report confirms the app calls it and your add is load-bearing. |
| `required` | Fail the run when this hook can't attach. Leave unset (or `false`) for nice-to-have hooks — they warn instead. |

`forge patch --dry-run` verifies every declared hook against the app's main
binary (class table + method lists + selrefs, chained-fixup aware) and prints
a summary:

```
Dry run OK -- 4 operation(s) would apply.
Hooks: 151/159 attach (8 issue(s))
  ! YTSettings -[areHintsDisabled]: unverified -- class exists ... walk missed it
```

Statuses: `ok` (on the class), `ok-inherited` (on an ancestor or a system
superclass like UIView), `ok-system` (system class, selector referenced by the
app), `added` (the tweak provides it), `unverified` (class/selector exists but
the parser couldn't fully confirm — treat as a soft warning), `missing-class` /
`missing-selector` / `elsewhere` (the hook would silently no-op — these fail
the run when `required`).

Porting to a new app version becomes: bump `target.version`, run
`--dry-run`, read the hook report, and fix exactly the hooks the report flags.
`forge hooks manifest --dir <dylib-sources>` regenerates the `hooks:` block
from the tweak sources; `forge hooks diff --old A.ipa --new B.ipa
--patches patch.yaml` shows which hooks regressed between two versions.

## The manifest


Every run produces a structured manifest (`--verbose` prints it; the GUI shows
it in the result card):

```json
{
  "input_sha256": "...",
  "bundle_id": "com.example.synthetic",
  "version": "1.0.0",
  "build": "1",
  "patches_applied": [
    {"id": "zero-marker-bytes", "status": "applied", "message": "replaced 1 match(es) at [0]"}
  ],
  "files_added": [], "files_modified": [...], "files_removed": [],
  "macho_modified": [".../TestApp"],
  "profile": {"uuid": "...", "team_id": "...", "expiration": "..."},
  "output_sha256": "..."
}
```

Use it to verify exactly what changed (and what didn't) before installing.

## Common mistakes

- **Typo'd `bundle_id`** → real runs fail with "refusing to produce an
  unpatched IPA" (or dry-run warns). Check the target block first.
- **`expected_matches` wrong** → `binary_replace` reports
  "expected N match(es), found M at offsets [...]". Bump to the real count, or
  fix the pattern.
- **Replacement length mismatch** → `binary_replace` fails; count the hex
  tokens in `pattern` vs `replacement`.
- **Missing `arch` on a fat binary** → add `arch: arm64` (or whichever slice
  you intend).
- **`resource_add` to an existing path** → use `resource_replace`.
- **`resource_replace` to a missing path** → use `resource_add`.
- **`dylib_inject` without staging the dylib** → pair it with `resource_add`
  (see above); the load will fail at runtime if the file isn't in the bundle.
- **Forgetting the dylib must also be signed** — it is: flat dylibs are signed
  individually and frameworks via their bundle directory.
