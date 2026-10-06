# SPDX-License-Identifier: GPL-3.0-or-later
"""Hook block signature vs method type encoding (hooks/signature.py).

The three mismatch cases are real bugs from a Spotify 9.1.88 port: each
compiled, passed `forge hooks verify`, and would have corrupted memory."""

from __future__ import annotations

from ipa_forge.hooks.scan import parse_block_literal
from ipa_forge.hooks.signature import check_block_signature, split_encoding


def test_split_encoding_skips_self_and_cmd():
    assert split_encoding("v32@0:8@16q24") == ("v", ["@", "q"])
    # a block argument (@?) is ONE token, not '@' followed by '?'
    assert split_encoding("v48@0:8@16@24@32@?40") == ("v", ["@", "@", "@", "@?"])
    assert split_encoding("v32@0:8@?<v@?B>16q24") == ("v", ["@?<v@?B>", "q"])


def test_nsinteger_typed_as_object_is_flagged():
    # -[SPTAuthSessionImplementation logoutWithReason:] is v24@0:8q16
    issues = check_block_signature("v24@0:8q16", "void", ["id self", "id reason"])
    assert len(issues) == 1 and "object vs scalar" in issues[0]


def test_bool_return_hooked_as_void_is_flagged():
    # -[SPTEncorePopUpPresenter presentPopUp:] is B24@0:8@16
    issues = check_block_signature("B24@0:8@16", "void", ["id self", "id popUp"])
    assert issues and "return" in issues[0] and "void vs value" in issues[0]


def test_unsigned_char_read_as_nsinteger_is_flagged():
    # -[ARTSRWebSocket _handleFrameWithData:opCode:] is v28@0:8@16C24
    issues = check_block_signature("v28@0:8@16C24", "void", ["id self", "NSData *data", "NSInteger opCode"])
    assert len(issues) == 1 and "8-bit" in issues[0] and "64-bit" in issues[0]


def test_correct_signatures_pass():
    assert check_block_signature("v24@0:8q16", "void", ["id self", "NSInteger reason"]) == []
    assert check_block_signature("B24@0:8@16", "BOOL", ["id self", "id popUp"]) == []
    assert check_block_signature("v28@0:8@16C24", "void", ["id self", "NSData *d", "uint8_t op"]) == []
    # any object pointer type matches @, blocks match @?
    assert (
        check_block_signature(
            "v40@0:8@16@24@?32", "void", ["id self", "NSURLSession *s", "NSString *x", "void (^h)(BOOL)"]
        )
        == []
    )
    # BOOL vs B and a 1-byte integer are the same width
    assert check_block_signature("v20@0:8B16", "void", ["id self", "BOOL on"]) == []


def test_omitting_trailing_arguments_is_allowed():
    assert check_block_signature("v32@0:8@16q24", "void", ["id self"]) == []


def test_extra_arguments_are_flagged():
    issues = check_block_signature("v16@0:8", "void", ["id self", "id extra"])
    assert issues and "only passes 0" in issues[0]


def test_inferred_return_and_unknown_types_are_not_judged():
    assert check_block_signature("B16@0:8", None, ["id self"]) == []  # ^(id self) -- inferred
    assert check_block_signature("v24@0:8{CGRect=dddd}16", "void", ["id self", "CGRect r"]) == []
    assert check_block_signature("v24@0:8^v16", "void", ["id self", "void *p"]) == []


def test_parse_block_literal_handles_nested_block_params():
    text = "(cls, @selector(x:y:), ^void(id self, NSInteger n, void (^done)(BOOL, NSError *)) { body(); })"
    pos = text.index(")") + 1  # just past @selector(...)
    ret, params = parse_block_literal(text, pos)
    assert ret == "void"
    assert params == ["id self", "NSInteger n", "void (^done)(BOOL, NSError *)"]


def test_parse_block_literal_without_return_or_params():
    assert parse_block_literal(", ^(id self) {", 0) == (None, ["id self"])
    assert parse_block_literal(", ^{ x(); }", 0) is None
    assert parse_block_literal(", someBlockVar)", 0) is None
