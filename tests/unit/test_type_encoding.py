# SPDX-License-Identifier: GPL-3.0-or-later
"""Objective-C type-encoding decoder: ivar/property types and full method
signatures reconstructed from runtime type-encoding strings."""

from __future__ import annotations

from ipa_forge.analysis.type_encoding import decode_method_signature, decode_type


def test_decode_simple_scalars() -> None:
    assert decode_type("i") == "int"
    assert decode_type("q") == "long long"
    assert decode_type("B") == "BOOL"
    assert decode_type("v") == "void"


def test_decode_object_pointer_with_class() -> None:
    assert decode_type('@"NSString"') == "NSString *"


def test_decode_id_without_class() -> None:
    assert decode_type("@") == "id"


def test_decode_protocol_qualified_id() -> None:
    assert decode_type('@"<NSCopying>"') == "id<NSCopying>"


def test_decode_pointer_to_scalar() -> None:
    assert decode_type("^i") == "int *"


def test_decode_struct_by_name() -> None:
    assert decode_type("{CGRect={CGPoint=dd}{CGSize=dd}}") == "struct CGRect"


def test_decode_no_arg_method_signature() -> None:
    # -(void)greet -- v (void ret), 16 (stack size), @0 (self), :8 (_cmd)
    assert decode_method_signature("greet", "v16@0:8") == "(void)greet"


def test_decode_single_arg_method_signature() -> None:
    # -(void)doIt:(id)arg -- v24@0:8@16
    assert decode_method_signature("doIt:", "v24@0:8@16") == "(void)doIt:(id)arg1"


def test_decode_object_return_method_signature() -> None:
    # +(id)makeIt -- @16@0:8
    assert decode_method_signature("makeIt", "@16@0:8") == "(id)makeIt"


def test_decode_missing_encoding_falls_back_untyped() -> None:
    assert decode_method_signature("greet", "") == "(id)greet"
    assert decode_method_signature("doIt:", "") == "doIt:(id)arg1"


def test_decode_multi_arg_method_signature() -> None:
    # -(void)setX:(int)x y:(int)y -- v32@0:8i16i24
    assert decode_method_signature("setX:y:", "v32@0:8i16i24") == "(void)setX:(int)arg1 y:(int)arg2"
