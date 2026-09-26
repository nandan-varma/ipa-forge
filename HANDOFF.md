# HANDOFF — engine ergonomics work (started 2026-09-25)

Working doc for an in-progress push to make investigation, patching, dry-runs
and verification faster and less error-prone, for humans and for AI sessions.
Delete this file when the checklist below is empty.

The findings came from an audit of the package, the docs, all five patch sets,
and the 453 bash commands recorded across eight prior Claude sessions in
`~/.claude/projects/-Users-nandan-dev-ipa-forge/*.jsonl` — that transcript
history is the evidence for the "measured" claims here and is worth re-reading
before changing priorities.

## Ground rules for this work

- `CLAUDE.md` (root + global) applies: smallest diff that solves it, no
  speculative abstractions, match surrounding style.
- Test-first for each item: write the failing test, then fix. Every item below
  names its verification.
- **Commit before and after each significant change** (the user asked for this
  explicitly). One item per commit; run
  `ruff format . && ruff check . && mypy ipa_forge/ && pytest tests/ -q`
  before each.
- Patch sets are all private submodules now (`.gitmodules`: youtube, spotify,
  instagram, shadowfight2, hillclimbracing2). **Commit inside the submodule
  first, then the pointer bump in the superproject** — a top-level `git add -A`
  silently skips submodule content.

## Baseline

`main` at the time of writing: `388d84e`. Suite: **243 passed**, coverage
~88% (gate is 80%). Start every session from a green suite.

---

## DONE (committed)

| Commit | What |
| --- | --- |
| `bea2fb4` | `perf`: exact `binary_replace` patterns scan via `bytes.find` instead of the per-byte Python loop. |
| `6af12c9` | `fix` (**A1–A3, C1 half**): closed three dry-run gate holes in `binary_replace`; capped offset lists in error messages; added `note:`/`symbol:` fields and byte-level evidence via `PatchResult.details`. |
| `a428414` | `chore`: shadowfight2 + hillclimbracing2 became private submodules (done by the user concurrently, not part of this work). |
| `98e1e87` | `perf` (**B1, A5**): content-addressed disk cache for `MachOAnalysis`; `analyze_bundle` now covers standalone `.dylib`s. |
| `388d84e` | `fix` (**A4, E2**): `unverified` no longer fails a run; three-way hook status reporting; filled in `verify.py`'s stale docstring. |

### What those changed, in case you need to reason about it

**A1–A3 (`ipa_forge/patch/binary.py`).** `BinaryReplaceOp.validate_patterns()`
parses `pattern` + `replacement` and checks they agree; `_plan()` calls it, so
`dry_run` and `apply` fail identically and neither raises. Previously a
length mismatch passed the gate and failed during apply, and a bad hex token
raised `PatternError` *out of* `apply` (a traceback from `run_pipeline`, after
earlier ops had already mutated the tree). `??` in a replacement is now
rejected — it used to silently write `0x00`. `format_offsets()` caps match
lists at 10 and prints hex; a bare `00` pattern used to produce a 1.7 MB
single-line message that travelled into `PipelineError` and the manifest.
`validate_patterns()` takes no bundle *on purpose* — item **D** reuses it.

**C1 half.** `PatchResult.details: dict[str, Any]` is merged into each
manifest entry by `Manifest.from_patch_results`. `binary_replace` fills it
with `offsets`, `before`, `after`, plus `note`/`symbol` when set.

**B1 (`ipa_forge/machO/cache.py`).** Keyed on SHA-256 of the binary, so a hit
survives re-extracting the same IPA to a new temp dir and a changed binary
can never hit a stale entry. `raw_data` is deliberately **not** stored —
re-reading it costs 0.07s, while shrinking it to a cstring set costs 7s, as
much as the parse being avoided. A hit restores it via `_slice_bytes()`, which
reads the arm64 slice's byte range, byte-identical to what `lipo -thin` would
write — otherwise `contains_string()` would search other architectures on a
hit but not on a miss. Measured on YouTube 21.38.2: `forge hooks find`
**10.0s → 1.7s**, byte-identical output. `forge cache` / `forge cache --clear`;
`FORGE_NO_CACHE=1` bypasses. `tests/conftest.py` has an autouse fixture
pointing `FORGE_CACHE_DIR` at a tmpdir — **never remove it**, or the suite
reads and writes the developer's real cache.

**A4.** `hooks/verify.py` exports `OK_STATUSES` and `BLOCKING_STATUSES`;
`HookResult` gained `.blocking` and `.unknown` beside `.ok`. Only the blocking
group can fail a run. `failing()` still returns not-ok (for display, so a
report surfaces parser gaps); `blocking()` is what the pipeline uses.

---

D is implemented: all five patch sets lint successfully; 15 new tests cover
schema/YAML errors, duplicate IDs, binary patterns, sources, and hooks.

## TODO

Ordered as recommended. Each item is independently shippable.

### D — `forge lint <yaml>`: IPA-free definition check — DONE

A 734-line definition (youtube) can only be checked today by a full dry-run
against a real IPA (5.6s, and you need the IPA on disk). There is no fast
syntax check, so a YAML edit has no tight feedback loop.

Also: **duplicate op `id`s are silently accepted** today and both land in the
manifest. Verified:
`build_operations` on two ops with `id: dup` returns `['dup', 'dup']`.

Implement `forge lint <definition.yaml>` doing, with no IPA:
1. schema validation via `load_patch_definition` (already produces a
   single-line error — reuse it, don't reinvent);
2. duplicate-`id` detection across `patches:` (new — belongs in
   `patch/schema.py` as a `model_validator`, so the pipeline gets it too);
3. `BinaryReplaceOp.validate_patterns()` per binary op — already bundle-free
   for exactly this;
4. existence of every `source:` file, resolved relative to the definition's
   parent directory (same rule as `PatchContext.patch_source_dir`);
5. duplicate `hooks:` entries (same class+selector twice is always a mistake).

Verify: unit tests per rule in `tests/unit/test_lint.py`; then
`forge lint patches/youtube/youtube.yaml` and each other set must pass, and a
deliberately broken copy must fail with a one-line message and exit 1.

### C2 — `forge patch --manifest out.json` ← **next**

Stage 10 "emits" a manifest that only exists in memory; `--verbose` prints it
to stdout and nothing writes it. Add `--manifest PATH`, written for dry-run
and real runs alike (a dry-run manifest is the useful "what would happen"
record, and now carries the byte-level evidence from C1).

Verify: CLI test asserting the file exists, parses as JSON, and contains the
`offsets`/`before`/`after` keys for a binary op.

### C3 — `forge verify-output --base <ipa> --output <ipa> [--manifest m.json]`

`patches/shadowfight2/tools/verify_output.py` (60 lines) hand-rolls something
generic: hash the base, replay each expected edit, assert the output binary
equals the reviewed bytes *and that no other file changed*. Promote it:
compare the two archives' Payload inventories, assert only the manifest's
`files_modified`/`added`/`removed` differ, and for each binary op assert the
bytes at its recorded `offsets` equal `after` and everything else is
unchanged. Then delete the per-patch script (see E3) and point
`patches/shadowfight2/PLAYBOOK.md` at the CLI.

Verify: integration test using `fixtures/synthetic_app.ipa` — patch it, then
`verify-output` must pass; flip one byte in the output and it must fail.

### B2/B3/B5 — query ergonomics

Driven by what prior sessions actually typed:

- **B2** `forge hooks find` takes exactly one selector, so the instagram
  session ran it in a `for` loop over 6 selectors — 6 full analyses for one
  question. Make the argument variadic (`nargs=-1`), analysing once.
- **B3** No `--json` anywhere except `patch --verbose`. Sessions
  post-processed human text with pipelines like
  `grep -A2 '^IGAdInsertionHandler : ' | tr ',' '\n' | sed 's/^ *//' | grep -iE '^(try|can|should|insert)'`.
  Add `--json` to `hooks verify`, `hooks find`, `hooks audit`, and
  `analysis classdump`.
- **B5** Add `--names-only` and `--methods-matching REGEX` to the class-dump
  path — that grep pipeline is asking for filters that do not exist.

Verify: CLI tests asserting `--json` output parses and contains the same facts
as the text form; a `--methods-matching` test on `objc_rich_macho_binary`.

### B4 — consolidate `hooks extract` into `analysis classdump`

`forge hooks extract` is a strict subset of `forge analysis classdump`: same
`--class`/`--search`, but classdump adds typed signatures, ivars, properties,
protocols and categories. Prior sessions used both interchangeably (42
classdump vs 16 extract calls) with no rule for which. Keep `classdump`; make
`hooks extract` a thin alias that prints a deprecation note, or remove it and
update the docs + playbooks. **Ask the user which** — removing a documented
command is their call.

### E1 — stale doc links in two patch sets

Five dead relative links survive the docs move to `docs/content/docs/*.mdx`
(0.1.1). An agent following the YouTube PLAYBOOK's *first instruction* opens a
file that does not exist:

- `patches/youtube/PLAYBOOK.md:4,6` → `../../docs/adding-an-app.md`,
  `../../docs/adding-a-feature.md`
- `patches/spotify/PLAYBOOK.md:4,76` → same two
- `patches/spotify/README.md:6,7` → same two

Correct target shape (already used by hillclimbracing2 and instagram):
`../../docs/content/docs/adding-an-app.mdx`. Two submodule commits + pointer
bumps.

### E3 — delete two superseded per-patch scripts

- `patches/youtube/tools/generate_hooks_manifest.py` (93 lines) duplicates
  `forge hooks manifest --dir dylib/ --inplace youtube.yaml`, and
  `PLAYBOOK.md` step 6 still tells you to run the script. Delete, point at
  the CLI.
- `patches/shadowfight2/tools/verify_output.py` — delete **after** C3 lands,
  not before.

### Patch-set improvements (needs C1 + C2 first)

- **shadowfight2** is the motivating case: 230 lines of 40-byte hex windows
  labelled by `id` only, with the real knowledge living in a hand-maintained
  `patch-evidence.json` (per-op `address`, owning `method`, `reason`,
  `before`/`after`, disassembly). Backfill `note:` from each entry's `reason`
  and `symbol:` from its `method` into `shadowfight2.yaml`, then regenerate
  evidence from `forge patch --manifest` and retire the hand-written file.
- **hillclimbracing2** is the same shape (pure `binary_replace` on a Unity
  binary) — give it `note:`/`symbol:` too, from `SOURCES.md`.
- Once `forge lint` exists, add it to every `PLAYBOOK.md` verify loop as the
  first step, ahead of the dry-run.

### Docs (do last, once behavior is settled)

- `docs/content/docs/patch-reference.mdx` — `note:`/`symbol:` on
  `binary_replace`; the `??`-in-replacement rejection; correct the hook-status
  table to the three-group model (it currently calls `unverified` a "soft
  warning" with `required: true`, which is now accurate but was not before).
- `docs/content/docs/usage.mdx` — `forge cache`, `FORGE_NO_CACHE`,
  `--manifest`, `forge lint`, `forge verify-output`, `--json`, the variadic
  `hooks find`.
- `docs/content/docs/architecture.mdx` — the cache in the component map; note
  that `analyze_bundle` covers frameworks **and** dylibs but not appexes, and
  why.
- `docs/content/docs/troubleshooting.mdx` — new messages: the replacement
  length/hex/wildcard errors, `forge lint` failures.
- `CHANGELOG.md` — one `## [Unreleased]` section covering all of the above.
- `CLAUDE.md` — mention `forge lint` and the cache in the commands block.

## Things deliberately NOT done

State these if asked, rather than re-deriving:

- **C4** (a `probe` mode reporting per-op "pattern still unique / not found"
  for byte-pattern sets on a new version) — `--dry-run` already computes this;
  wait until a second byte-pattern set actually needs porting.
- **A5 beyond the kinds fix** — no current patch set ships a bundled `.dylib`
  with hookable ObjC classes, so the fix has no live regression test. The
  synthetic fixture's `libInjectable.dylib` defines no classes.
- Replacing `MachOAnalysis.raw_data` with a cstring set — measured at 7.2s to
  build on YouTube's binary versus 0.07s to re-read the bytes. It would cost
  more than the parse it was meant to help.
- A `--no-cache` flag on all eight analysis-backed commands — the cache is
  content-addressed, so a stale hit is not a day-to-day failure mode.
  `FORGE_NO_CACHE=1` and `forge cache --clear` cover the real needs.

## Useful facts for the next session

- Base IPAs live in `~/Downloads/`: `com.google.ios.youtube_21.38.2_und3fined.ipa`,
  `com.burbn.instagram_448.0.0_und3fined.ipa`,
  `com.nekki.shadowfight_2.46.0_und3fined.ipa`,
  `com.fingersoft.hillclimbracing2-1.74.2-Decrypted.ipa`. The
  App-Store-shaped `*_544007664_*.ipa` files are **encrypted** and will
  dry-run fine but not run on device.
- Timings on YouTube 21.38.2 after the cache: `hooks find` 1.7s warm / 10.0s
  cold; `forge patch --dry-run` 5.6s, of which ~2.9s is `unzip`. Use
  `--app-dir` on an already-extracted bundle to skip that.
- Current YouTube hook report: `203/211 attach, 8 unverified, 0 failing`. All
  8 are known-benign parser gaps; if that number moves, something real
  changed.
