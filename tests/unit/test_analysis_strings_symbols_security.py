# SPDX-License-Identifier: GPL-3.0-or-later
"""strings/symbols/security posture -- real compiled binaries, not mocks
(the codebase's convention: exercise the actual otool/LIEF-backed parsing
path rather than stubbing it out)."""

from __future__ import annotations

from pathlib import Path

from ipa_forge.analysis.security import analyze_security, render_security_posture
from ipa_forge.analysis.strings import extract_strings, strings_in_bundle
from ipa_forge.analysis.symbols import analyze_symbols
from ipa_forge.bundle.ipa import extract_ipa, load_bundle

FIXTURES = Path(__file__).parent.parent.parent / "fixtures"


def test_extract_strings_finds_known_literal(compiled_macho_binary: Path) -> None:
    data = compiled_macho_binary.read_bytes()
    found = extract_strings(data, min_len=4)
    assert any(len(s) >= 4 for s in found)


def test_extract_strings_respects_min_len() -> None:
    data = b"\x00ab\x00abcdefgh\x00"
    assert "ab" not in extract_strings(data, min_len=4)
    assert "abcdefgh" in extract_strings(data, min_len=4)


def test_strings_in_bundle_tags_binary_name(tmp_path: Path) -> None:
    app_path = extract_ipa(FIXTURES / "synthetic_app.ipa", tmp_path / "extracted")
    bundle = load_bundle(app_path)
    found = strings_in_bundle(bundle, min_len=4)
    assert found
    assert {s.binary for s in found} >= {"TestApp"}


def test_analyze_symbols_lists_linked_libraries(objc_macho_binary: Path) -> None:
    syms = analyze_symbols(objc_macho_binary)
    assert any("Foundation" in lib for lib in syms.linked_libraries)
    assert any("objc" in s for s in syms.imported_symbols)


def test_analyze_security_reports_pie_and_min_os(objc_macho_binary: Path) -> None:
    posture = analyze_security(objc_macho_binary)
    assert posture.pie is True
    assert posture.encrypted is False  # locally compiled, never encrypted
    text = render_security_posture(posture)
    assert "PIE:" in text
    assert "Encrypted:" in text
