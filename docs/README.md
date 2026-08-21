# ipa-forge documentation

Which document to read, for what. **New session? Start with
[`../STATE.md`](../STATE.md)** — the project state & operating knowledge —
then come back here for the map.

## For humans adding a new app, feature, or patch

| You want to... | Read |
| --- | --- |
| Port a **new app** (new IPA, new bundle id) | [`adding-an-app.md`](adding-an-app.md) — the end-to-end playbook |
| Add a **feature** to an existing hook dylib | [`adding-a-feature.md`](adding-a-feature.md) — the conventions |
| Understand the **patch definition YAML** (`target`/`patches`/`hooks`) | [`patch-reference.md`](patch-reference.md) |
| Use the **CLI** (`forge patch`, `forge hooks …`, …) | [`usage.md`](usage.md) |
| **Reverse engineer** an IPA (`forge analysis …`: class-dump, strings, symbols, security, diff) | [`reverse-engineering.md`](reverse-engineering.md) |
| Debug an **error message** | [`troubleshooting.md`](troubleshooting.md) |
| Test on a **real device** via AltStore | [`altstore_device_testing.md`](altstore_device_testing.md) |
| Understand **how the engine works** (for developers) | [`architecture.md`](architecture.md) |
| Extend the engine (new operation type, new provider) | [`extensibility.md`](extensibility.md) |
| See what's **deferred/future work** on the RE tooling (disassembly, etc.) | [`../ROADMAP.md`](../ROADMAP.md) |

## The patch sets (concrete worked examples)

Patch definitions live in **separate private repos** (submoduled under `patches/` — requires auth). Clone with `git clone --recursive`.

| Patch set | Docs | Repo |
| --- | --- | --- |
| YouTube 21.32.4 (`patches/youtube/`) | [`PLAYBOOK.md`](../patches/youtube/PLAYBOOK.md) (runbook), [`README.md`](../patches/youtube/README.md) (features), [`ROADMAP.md`](../patches/youtube/ROADMAP.md) (goals), [`SOURCES.md`](../patches/youtube/SOURCES.md) (attribution) | [`nandan-varma/ipa-forge-patches-youtube`](https://github.com/nandan-varma/ipa-forge-patches-youtube) (private) |
| Spotify 9.1.72 (`patches/spotify/`) | [`PLAYBOOK.md`](../patches/spotify/PLAYBOOK.md) (runbook), [`README.md`](../patches/spotify/README.md) (features), [`SOURCES.md`](../patches/spotify/SOURCES.md) | [`nandan-varma/ipa-forge-patches-spotify`](https://github.com/nandan-varma/ipa-forge-patches-spotify) (private) |
| Instagram 442.0.0 (`patches/instagram/`) | [`PLAYBOOK.md`](../patches/instagram/PLAYBOOK.md) (runbook), [`README.md`](../patches/instagram/README.md) (features), [`SOURCES.md`](../patches/instagram/SOURCES.md) | [`nandan-varma/ipa-forge-patches-instagram`](https://github.com/nandan-varma/ipa-forge-patches-instagram) (private) |

## The reading order for a new session

1. **`adding-an-app.md`** — if the task is "here's an IPA, port everything".
2. **`adding-a-feature.md`** — if the task is "add X to the mod".
3. `patch-reference.md` + `usage.md` — for the exact YAML/CLI surface.
4. `troubleshooting.md` — when something breaks.
5. The patch set's `PLAYBOOK.md` — the concrete workflow for that app.

## Related

- [`adding-an-app.md`](adding-an-app.md) / [`adding-a-feature.md`](adding-a-feature.md) — the how-to guides
- [`reverse-engineering.md`](reverse-engineering.md) — `forge analysis` (class-dump, strings, symbols, security, diff)
- The patch-set `PLAYBOOK.md` files — worked examples
