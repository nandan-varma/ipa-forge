from __future__ import annotations

from pathlib import Path

from ipa_forge.bundle.ipa import extract_ipa, load_bundle
from ipa_forge.patch.base import PatchContext
from ipa_forge.patch.resource import ResourceAddOp, ResourceRemoveOp, ResourceReplaceOp


def _bundle_ctx(tmp_path: Path, fake_ipa: Path, patch_source_dir: Path):
    app_path = extract_ipa(fake_ipa, tmp_path / "extract")
    bundle = load_bundle(app_path)
    return PatchContext(bundle=bundle, patch_source_dir=patch_source_dir)


def test_resource_replace_applies(tmp_path: Path, fake_ipa: Path):
    source_dir = tmp_path / "sources"
    source_dir.mkdir()
    (source_dir / "new.txt").write_text("patched content\n")

    ctx = _bundle_ctx(tmp_path, fake_ipa, source_dir)
    op = ResourceReplaceOp(op_id="r1", path="resource.txt", source="new.txt")

    assert op.dry_run(ctx).status == "dry_run_ok"
    result = op.apply(ctx)
    assert result.status == "applied"
    assert (ctx.bundle.root / "resource.txt").read_text() == "patched content\n"


def test_resource_replace_fails_if_destination_missing(tmp_path: Path, fake_ipa: Path):
    source_dir = tmp_path / "sources"
    source_dir.mkdir()
    (source_dir / "new.txt").write_text("x")

    ctx = _bundle_ctx(tmp_path, fake_ipa, source_dir)
    op = ResourceReplaceOp(op_id="r2", path="does_not_exist.txt", source="new.txt")
    assert op.dry_run(ctx).status == "failed"


def test_resource_add_creates_new_file(tmp_path: Path, fake_ipa: Path):
    source_dir = tmp_path / "sources"
    source_dir.mkdir()
    (source_dir / "extra.txt").write_text("brand new\n")

    ctx = _bundle_ctx(tmp_path, fake_ipa, source_dir)
    op = ResourceAddOp(op_id="r3", path="nested/extra.txt", source="extra.txt")

    result = op.apply(ctx)
    assert result.status == "applied"
    assert (ctx.bundle.root / "nested" / "extra.txt").read_text() == "brand new\n"


def test_resource_add_fails_if_destination_exists(tmp_path: Path, fake_ipa: Path):
    source_dir = tmp_path / "sources"
    source_dir.mkdir()
    (source_dir / "extra.txt").write_text("x")

    ctx = _bundle_ctx(tmp_path, fake_ipa, source_dir)
    op = ResourceAddOp(op_id="r4", path="resource.txt", source="extra.txt")
    assert op.dry_run(ctx).status == "failed"


def test_resource_remove_deletes_file(tmp_path: Path, fake_ipa: Path):
    ctx = _bundle_ctx(tmp_path, fake_ipa, tmp_path)
    op = ResourceRemoveOp(op_id="r5", path="resource.txt")

    result = op.apply(ctx)
    assert result.status == "applied"
    assert not (ctx.bundle.root / "resource.txt").exists()


def test_resource_path_traversal_is_rejected(tmp_path: Path, fake_ipa: Path):
    ctx = _bundle_ctx(tmp_path, fake_ipa, tmp_path)
    op = ResourceRemoveOp(op_id="r6", path="../../etc/passwd")
    result = op.dry_run(ctx)
    assert result.status == "failed"
    assert "escapes" in result.message
