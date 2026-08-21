# SPDX-License-Identifier: GPL-3.0-or-later
"""Class-dump rendering: real compiled ObjC metadata -> `.h`-style text."""

from __future__ import annotations

from pathlib import Path

from ipa_forge.analysis.classdump import render_analysis, render_category, render_class, render_protocol
from ipa_forge.machO.objc import analyze_macho


def test_render_class_shows_superclass_protocol_ivar_property_methods(objc_rich_macho_binary: Path) -> None:
    analysis = analyze_macho(objc_rich_macho_binary)
    text = render_class(analysis.classes["Bar"])
    # NSObject is defined in Foundation, not this image -- honestly reported
    # as "«external»" (same convention as hook verification), never guessed.
    assert "@interface Bar : «external» <Greeter>" in text
    assert "int _count;" in text
    assert "NSString *label;" in text  # @property NSString *label;
    assert "- (void)greet;" in text
    assert "- (void)wave;" in text
    assert text.strip().endswith("@end")


def test_render_protocol_separates_required_and_optional(objc_rich_macho_binary: Path) -> None:
    analysis = analyze_macho(objc_rich_macho_binary)
    text = render_protocol(analysis.protocols["Greeter"])
    assert text.startswith("@protocol Greeter")
    assert "- (void)greet;" in text.split("@optional")[0]
    assert "- (void)wave;" in text.split("@optional")[1]


def test_render_category_shows_extended_class(objc_rich_macho_binary: Path) -> None:
    analysis = analyze_macho(objc_rich_macho_binary)
    cat = analysis.categories[0]
    text = render_category(cat)
    assert text.startswith(f"@interface {cat.class_name} (Extras)")
    assert "- (void)extraThing;" in text


def test_render_analysis_includes_everything(objc_rich_macho_binary: Path) -> None:
    analysis = analyze_macho(objc_rich_macho_binary)
    text = render_analysis(analysis)
    assert "@protocol Greeter" in text
    assert "@interface Bar : «external»" in text
    assert "(Extras)" in text


def test_render_analysis_class_filter_restricts_output(objc_rich_macho_binary: Path) -> None:
    analysis = analyze_macho(objc_rich_macho_binary)
    text = render_analysis(analysis, class_filter="Bar")
    assert "@interface Bar" in text
    assert "@protocol Greeter" not in text
    assert "(Extras)" not in text


def test_render_analysis_search_filters_by_regex(objc_rich_macho_binary: Path) -> None:
    analysis = analyze_macho(objc_rich_macho_binary)
    text = render_analysis(analysis, search="^Ba")
    assert "@interface Bar" in text
    assert "@protocol Greeter" not in text
