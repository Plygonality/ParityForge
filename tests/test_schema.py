from __future__ import annotations

import json
from pathlib import Path

import pytest

from parityforge.errors import SchemaError
from parityforge.migrations import migrate
from parityforge.snapshot_io import load_snapshot, save_snapshot


def test_fixture_validates(tmp_path: Path) -> None:
    loaded = load_snapshot(Path("fixtures/transformed_primitive/blender.snapshot.json"))
    assert loaded.model.schema_version == "1.0.0"
    assert loaded.objects[0].points is not None
    assert loaded.objects[0].points.shape == (4, 3)


def test_malformed_json_names_the_location(tmp_path: Path) -> None:
    path = tmp_path / "broken.snapshot.json"
    path.write_text("{", encoding="utf-8")
    with pytest.raises(SchemaError) as caught:
        load_snapshot(path)
    assert "Malformed JSON" in str(caught.value)
    assert "line" in str(caught.value)


def test_missing_fields_are_actionable(tmp_path: Path) -> None:
    path = tmp_path / "partial.snapshot.json"
    path.write_text(json.dumps({"schema_version": "1.0.0"}) + "\n", encoding="utf-8")
    with pytest.raises(SchemaError) as caught:
        load_snapshot(path)
    text = str(caught.value)
    assert "identity" in text
    assert "docs/schema.md" in text


def test_unknown_schema_version_is_rejected() -> None:
    with pytest.raises(SchemaError) as caught:
        migrate({"schema_version": "2.0.0"})
    assert "2.0.0" in str(caught.value)
    assert "1.0.0" in str(caught.value)


def test_registered_migration_rewrites_and_cycles_fail() -> None:
    def upgrade(document: dict) -> dict:
        renamed = dict(document)
        renamed["schema_version"] = "1.0.0"
        renamed["coordinate_basis"] = renamed.pop("basis")
        return renamed

    migrated = migrate({"schema_version": "0.9.0", "basis": "houdini"}, registry={"0.9.0": upgrade})
    assert migrated["schema_version"] == "1.0.0"
    assert migrated["coordinate_basis"] == "houdini"

    def loop(document: dict) -> dict:
        return {"schema_version": "0.9.0"}

    with pytest.raises(SchemaError) as caught:
        migrate({"schema_version": "0.9.0"}, registry={"0.9.0": loop})
    assert "cycle" in str(caught.value)


def test_hash_mismatch_is_not_ignored(tmp_path: Path) -> None:
    source = Path("fixtures/transformed_primitive/blender.snapshot.json")
    path = tmp_path / "edited.snapshot.json"
    document = json.loads(source.read_text(encoding="utf-8"))
    document["identity"]["scene"] = "tampered"
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(SchemaError) as caught:
        load_snapshot(path)
    assert "hash mismatch" in str(caught.value).lower()


def test_large_inline_arrays_are_rejected(tmp_path: Path) -> None:
    source = json.loads(Path("fixtures/transformed_primitive/blender.snapshot.json").read_text(encoding="utf-8"))
    source["objects"][0]["geometry"]["point_count"] = 100_001
    source["objects"][0]["geometry"]["points"] = [[0.0, 0.0, 0.0]] * 100_001
    path = tmp_path / "huge.snapshot.json"
    with pytest.raises(SchemaError) as caught:
        save_snapshot(path, source)
    assert "NPZ" in str(caught.value)
