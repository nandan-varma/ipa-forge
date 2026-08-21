# Reverse Engineering an IPA (`forge analysis`)

General-purpose, read-only static analysis of any `.ipa` — not tied to a
specific patch set or app. Built on the same Mach-O/ObjC analysis engine
(`ipa_forge/machO/objc.py`) that `forge hooks` uses to verify hook targets;
see [`architecture.md`](architecture.md#component-map) for how the two
relate. Every command accepts `--app-dir <Payload/App.app>` in place of
`--ipa` to skip re-extraction while iterating, same as `forge hooks`.

## Scope boundary

Two things are deliberately **not** implemented, by design rather than
oversight — see [`ROADMAP.md`](../ROADMAP.md) for the reasoning and what
would be involved in adding them later:

- **FairPlay/App Store DRM decryption.** Every command here assumes an
  already-decrypted `.ipa`, exactly like the rest of ipa-forge.
- **Instruction-level disassembly/decompilation.** Static metadata
  (classes, strings, symbols) only — no capstone/Ghidra-style disassembly.

## `forge analysis classdump`

Dumps the app's Objective-C runtime metadata as `.h`-style class-dump text:
every class (superclass, protocol conformance, ivars, properties, full
method signatures reconstructed from type encodings), protocol
declarations, and categories.

```bash
forge analysis classdump --ipa App.ipa
forge analysis classdump --ipa App.ipa --class YTPlayerViewController
forge analysis classdump --ipa App.ipa --search '^YT' --output dump.h
```

`--class`/`--search` restrict output to matching classes only (protocols
and categories are omitted in that case, matching `forge hooks extract`'s
`--class`/`--search`). A class/superclass defined in another image (system
frameworks, or a framework you didn't point the tool at) is reported as
`«external»` — the same honest-reporting convention `forge hooks` uses,
rather than guessing.

The type-encoding decoder (`ipa_forge/analysis/type_encoding.py`) is
best-effort: structs/unions render as just their tag name (no field
expansion), and truly exotic encodings fall back to the raw string. Good
enough to read; not good enough to regenerate a compilable header.

## `forge analysis strings`

Printable-ASCII string extraction across every executable in the bundle
(main + frameworks + dylibs + extensions), tagged with which binary each
string came from.

```bash
forge analysis strings --ipa App.ipa --min-len 6
forge analysis strings --ipa App.ipa --search 'https?://' --binary MainExecutable
```

Pipe to `grep` for anything `--search` doesn't cover directly — no output
cap (unlike the GUI's `/analysis` page, which caps at 2000 matches for
browser sanity).

## `forge analysis symbols`

Linked libraries and imported/exported symbols for one executable in the
bundle (`otool -L` + `nm`, backed by LIEF's structured symbol table instead
of parsing text) — default target is the main executable; `--binary
<substring>` selects another (a framework, an extension, a standalone
dylib). `--arch` is required if the target is a universal binary.

```bash
forge analysis symbols --ipa App.ipa
forge analysis symbols --ipa App.ipa --binary SomeFramework
```

## `forge analysis security`

Read-only build/security posture for one executable: PIE, an
encryption-flag check (`LC_ENCRYPTION_INFO`'s `cryptid` — **detection
only, never decryption**), stack protector, an ARC heuristic
(`_objc_storeStrong`/`_objc_release` imported — not definitive), min-OS,
and platform.

```bash
forge analysis security --ipa App.ipa
```

## `forge analysis diff`

Survey of what changed between two builds of the same app: classes and
protocols added/removed, per-class method churn, and `Info.plist` key
changes. Purely informational — exit code is always 0 regardless of
findings.

```bash
forge analysis diff --old App_1.0.ipa --new App_2.0.ipa
```

This is **broader but shallower** than `forge hooks diff`
(see [`usage.md`](usage.md#generating-and-diffing-hook-manifests)): `forge
hooks diff` only re-checks one patch definition's *declared* hook targets
and is a pass/fail gate (exit 1 on a required-hook regression); `forge
analysis diff` surveys everything that changed, independent of any patch
set, and never fails the exit code. Use `forge hooks diff` to gate a patch
set's CI; use `forge analysis diff` to understand *what* changed before
writing the patch set in the first place.

Entitlements are intentionally not diffed here: reading them requires
shelling out to `codesign`/`security`, and `signing/backend.py` is the only
module allowed to do that (architecture.md's hard constraint) — a real
entitlements diff belongs in that subsystem, not in this read-only,
signing-independent package.

## The web GUI (`forge gui` → `/analysis`)

The same four views (class-dump, strings, security, diff), browsable
without installing the CLI: `forge gui` → open the link in the main
patcher page's subtitle, or navigate directly to
`http://127.0.0.1:8765/analysis`. Single-user, local-only, same as the
patch-flow page — see [`usage.md`](usage.md#the-web-gui).

## Related

- [`architecture.md`](architecture.md) — the `machO/objc.py` analysis engine `hooks/` and `analysis/` share
- [`usage.md`](usage.md) — `forge hooks` and the rest of the CLI
- [`ROADMAP.md`](../ROADMAP.md) — deferred phases (disassembly) and why they're deferred
- [`README.md`](README.md) — docs index
