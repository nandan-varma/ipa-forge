from __future__ import annotations

from pathlib import Path

from ipa_forge.bundle.ipa import extract_ipa, load_bundle
from ipa_forge.bundle.plist import read_plist
from ipa_forge.patch.base import PatchContext
from ipa_forge.patch.plist import PlistEditOp
from ipa_forge.patch.schema import PatchDefinition


def _bundle_ctx(tmp_path: Path, fake_ipa: Path) -> PatchContext:
    app_path = extract_ipa(fake_ipa, tmp_path / "extract")
    bundle = load_bundle(app_path)
    return PatchContext(bundle=bundle, patch_source_dir=tmp_path)


def test_set_adds_or_overwrites_a_key(tmp_path: Path, fake_ipa: Path):
    ctx = _bundle_ctx(tmp_path, fake_ipa)
    op = PlistEditOp(op_id="p1", action="set", key="MinimumOSVersion", value="14.0")

    assert op.dry_run(ctx).status == "dry_run_ok"
    result = op.apply(ctx)
    assert result.status == "applied"

    plist = read_plist(ctx.bundle.root / "Info.plist")
    assert plist["MinimumOSVersion"] == "14.0"


def test_remove_deletes_an_existing_key(tmp_path: Path, fake_ipa: Path):
    ctx = _bundle_ctx(tmp_path, fake_ipa)
    op = PlistEditOp(op_id="p2", action="remove", key="CFBundleVersion")

    result = op.apply(ctx)
    assert result.status == "applied"

    plist = read_plist(ctx.bundle.root / "Info.plist")
    assert "CFBundleVersion" not in plist


def test_remove_fails_if_key_absent(tmp_path: Path, fake_ipa: Path):
    ctx = _bundle_ctx(tmp_path, fake_ipa)
    op = PlistEditOp(op_id="p3", action="remove", key="NoSuchKey")
    result = op.dry_run(ctx)
    assert result.status == "failed"
    assert "not present" in result.message


def test_set_requires_a_value_in_schema():
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        PatchDefinition.model_validate(
            {
                "target": {"bundle_id": "com.example.test", "version": {"exact": "1.0.0"}},
                "patches": [{"type": "plist_edit", "id": "x", "action": "set", "key": "Foo"}],
            }
        )


def test_plist_edit_spec_parses_and_builds_operation():
    from ipa_forge.patch.loader import build_operations

    definition = PatchDefinition.model_validate(
        {
            "target": {"bundle_id": "com.example.test", "version": {"exact": "1.0.0"}},
            "patches": [
                {"type": "plist_edit", "id": "x", "action": "set", "key": "Foo", "value": "bar"},
                {"type": "plist_edit", "id": "y", "action": "remove", "key": "Baz", "path": "Frameworks/F.framework/Info.plist"},
            ],
        }
    )
    ops = build_operations(definition)
    assert len(ops) == 2
    assert ops[0].key == "Foo" and ops[0].value == "bar" and ops[0].path == "Info.plist"
    assert ops[1].key == "Baz" and ops[1].path == "Frameworks/F.framework/Info.plist"
