# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import os
from pathlib import Path

import pytest

from ipa_forge.machO import cache
from ipa_forge.machO.objc import analyze_macho, contains_string


def test_cache_dir_prefers_forge_cache_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("FORGE_CACHE_DIR", str(tmp_path / "explicit"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg"))
    assert cache.cache_dir() == tmp_path / "explicit"


def test_cache_dir_falls_back_to_xdg(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.delenv("FORGE_CACHE_DIR", raising=False)
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg"))
    assert cache.cache_dir() == tmp_path / "xdg" / "ipa-forge"


def test_load_is_a_miss_when_nothing_is_cached(objc_macho_binary: Path):
    assert cache.load(objc_macho_binary) is None


def test_round_trip_restores_the_analysis(objc_macho_binary: Path):
    original = analyze_macho(objc_macho_binary, use_cache=False)
    cache.store(objc_macho_binary, original)

    cached = cache.load(objc_macho_binary)
    assert cached is not None
    assert set(cached.classes) == set(original.classes)
    assert cached.classes["Foo"].inst == original.classes["Foo"].inst
    assert cached.selectors == original.selectors


def test_store_leaves_the_live_analysis_untouched(objc_macho_binary: Path):
    """store() blanks raw_data/main_executable to keep the entry small, and must
    put them back -- the caller goes on using the same object."""
    analysis = analyze_macho(objc_macho_binary, use_cache=False)
    raw_before, main_before = analysis.raw_data, analysis.main_executable

    cache.store(objc_macho_binary, analysis)

    assert analysis.raw_data is raw_before and analysis.raw_data
    assert analysis.main_executable == main_before


def test_analyze_macho_hit_matches_a_fresh_parse(objc_macho_binary: Path):
    fresh = analyze_macho(objc_macho_binary, use_cache=False)
    analyze_macho(objc_macho_binary)  # populates the cache
    hit = analyze_macho(objc_macho_binary)

    assert set(hit.classes) == set(fresh.classes)
    assert hit.selectors == fresh.selectors
    assert hit.main_executable == objc_macho_binary
    # raw_data must be restored on a hit: the verifier's string cross-check
    # depends on it, and an empty list would silently turn `unverified` results
    # into hard `missing-class` failures.
    assert contains_string(hit, "Foo") == contains_string(fresh, "Foo")


def test_fat_binary_hit_holds_only_the_arm64_slice(fat_macho_binary: Path):
    """A cache hit must hold the same bytes as a miss. A fresh parse thins the
    binary first, so raw_data is the arm64 slice, not the whole fat file."""
    fresh = analyze_macho(fat_macho_binary, use_cache=False)
    analyze_macho(fat_macho_binary)
    hit = analyze_macho(fat_macho_binary)

    assert len(hit.raw_data) == 1
    assert len(hit.raw_data[0]) < fat_macho_binary.stat().st_size
    assert hit.raw_data[0] == fresh.raw_data[0]


def test_a_changed_binary_never_hits_a_stale_entry(objc_macho_binary: Path):
    analyze_macho(objc_macho_binary)
    data = bytearray(objc_macho_binary.read_bytes())
    data[-1] ^= 0xFF  # same size, same mtime granularity, different content
    objc_macho_binary.write_bytes(bytes(data))

    assert cache.load(objc_macho_binary) is None


def test_corrupt_entry_is_a_miss_not_an_error(objc_macho_binary: Path):
    analyze_macho(objc_macho_binary)
    entry = next((cache.cache_dir() / "objc").glob("*.pickle"))
    entry.write_bytes(b"not a pickle")

    assert cache.load(objc_macho_binary) is None
    # and the command still works, repopulating the entry
    assert analyze_macho(objc_macho_binary).classes


def test_store_survives_an_unwritable_cache_dir(
    objc_macho_binary: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    blocked = tmp_path / "blocked"
    blocked.mkdir()
    blocked.chmod(0o500)
    monkeypatch.setenv("FORGE_CACHE_DIR", str(blocked))
    try:
        analysis = analyze_macho(objc_macho_binary, use_cache=False)
        cache.store(objc_macho_binary, analysis)  # must not raise
        assert analysis.raw_data  # still intact for the caller
    finally:
        blocked.chmod(0o700)


def test_eviction_keeps_the_cache_bounded(objc_macho_binary: Path):
    """Entries are tens of MB; walking many app versions must not grow the
    cache without bound."""
    analysis = analyze_macho(objc_macho_binary, use_cache=False)
    scratch = objc_macho_binary.parent / "variant"
    data = bytearray(objc_macho_binary.read_bytes())
    for i in range(cache._MAX_ENTRIES + 4):
        data[-1] = i & 0xFF
        scratch.write_bytes(bytes(data))
        cache.store(scratch, analysis)

    entries = list((cache.cache_dir() / "objc").glob("*.pickle"))
    assert len(entries) == cache._MAX_ENTRIES
    assert not list((cache.cache_dir() / "objc").glob("*.tmp"))


def test_clear_removes_every_entry(objc_macho_binary: Path):
    analyze_macho(objc_macho_binary)
    assert cache.clear() == 1
    assert cache.load(objc_macho_binary) is None
    assert cache.clear() == 0


def test_clear_on_a_never_used_cache_is_not_an_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("FORGE_CACHE_DIR", str(tmp_path / "absent"))
    assert cache.clear() == 0


def test_cache_is_isolated_from_the_real_home_dir():
    """The autouse fixture in conftest must be in force: a test run should never
    touch the developer's real cache."""
    assert "FORGE_CACHE_DIR" in os.environ
    assert Path.home() not in cache.cache_dir().parents
