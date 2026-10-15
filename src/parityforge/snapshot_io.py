"""Load and save JSON + NPZ snapshots."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from pydantic import ValidationError

from .errors import SchemaError
from .migrations import CURRENT_SCHEMA, migrate
from .models import MAX_INLINE, Snapshot, check_basis

Array = np.ndarray


@dataclass
class LoadedAttribute:
    name: str
    domain: str
    type: str
    role: str
    values: Array


@dataclass
class LoadedObject:
    name: str
    path: str
    type: str
    transform: Array
    geometry_space: str | None
    points: Array | None
    faces: list[list[int]] | None
    correspondence: str
    instance_space: str | None
    instance_positions: Array | None
    instance_ids: Array | None
    instance_correspondence: str
    instance_prototype: str | None
    instance_count: int | None
    attributes: list[LoadedAttribute] = field(default_factory=list)


@dataclass
class LoadedSnapshot:
    model: Snapshot
    path: Path
    objects: list[LoadedObject]


def _canonical_bytes(document: dict[str, Any]) -> bytes:
    body = {key: value for key, value in document.items() if key != "hashes"}
    payload = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return payload.encode("utf-8")


def metadata_sha256(document: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_bytes(document)).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _format_validation(exc: ValidationError) -> str:
    lines = ["Snapshot validation failed."]
    for error in exc.errors():
        loc = ".".join(str(part) for part in error["loc"]) or "(root)"
        lines.append(f"  - {loc}: {error['msg']}")
    lines.append(f'Hint: see docs/schema.md for snapshot schema {CURRENT_SCHEMA}.')
    return "\n".join(lines)


def _safe_relative(base: Path, relative: str) -> Path:
    if not relative or relative.startswith(("/", "\\")) or ".." in Path(relative).parts:
        raise SchemaError(
            f"Array path {relative!r} must be a relative file inside the snapshot directory.",
            hint="Use a filename such as points.npz with no parent segments.",
        )
    path = (base / relative).resolve()
    if path.parent != base.resolve():
        raise SchemaError(
            f"Array path {relative!r} escapes the snapshot directory.",
            hint="Keep NPZ files next to the snapshot JSON.",
        )
    return path


def _load_npz_array(base: Path, filename: str, key: str) -> Array:
    path = _safe_relative(base, filename)
    if not path.is_file():
        raise SchemaError(
            f"Missing array file {filename} referenced by the snapshot.",
            hint=f"Expected {path}.",
        )
    try:
        with np.load(path) as data:
            if key not in data:
                raise SchemaError(
                    f"{filename} has no array {key!r}.",
                    hint=f"Arrays in the file: {sorted(data.files)}.",
                )
            return np.array(data[key])
    except SchemaError:
        raise
    except Exception as exc:
        raise SchemaError(f"Could not read {filename}: {exc}") from exc


def _exclusive(inline: Any, npz: str | None, *, what: str) -> None:
    if inline is not None and npz is not None:
        raise SchemaError(f"{what} sets both inline data and an NPZ reference. Use only one.")
    if inline is None and npz is None:
        raise SchemaError(f"{what} has neither inline data nor an NPZ reference.")


def _as_points(array: Array, *, what: str) -> Array:
    points = np.asarray(array, dtype=float)
    if points.ndim != 2 or points.shape[1] != 3:
        raise SchemaError(f"{what} must have shape (N, 3), got {points.shape}.")
    if not np.all(np.isfinite(points)):
        raise SchemaError(f"{what} contains a non-finite coordinate.")
    return points


def _decode_faces(counts: Array, indices: Array, *, what: str) -> list[list[int]]:
    counts_i = np.asarray(counts, dtype=int)
    indices_i = np.asarray(indices, dtype=int)
    faces: list[list[int]] = []
    cursor = 0
    for count in counts_i.tolist():
        if count < 3:
            raise SchemaError(f"{what} has a face with {count} vertices. Faces need at least 3.")
        nxt = cursor + count
        if nxt > len(indices_i):
            raise SchemaError(f"{what} face_indices ended before face_counts was consumed.")
        faces.append(indices_i[cursor:nxt].tolist())
        cursor = nxt
    if cursor != len(indices_i):
        raise SchemaError(
            f"{what} face_indices length {len(indices_i)} does not match face_counts sum {cursor}."
        )
    return faces


def _load_attribute(base: Path, raw: Any) -> LoadedAttribute:
    label = f"attribute {raw.name!r}"
    if raw.inline is None and raw.npz is None:
        raise SchemaError(
            f"{label} has no values.",
            hint="Set inline or npz/key. Missing values are not treated as a match.",
        )
    _exclusive(raw.inline, raw.npz, what=label) if raw.inline is not None or raw.npz is not None else None
    if raw.inline is not None and raw.npz is not None:
        raise SchemaError(f"{label} sets both inline data and an NPZ reference.")
    if raw.npz is not None:
        if not raw.key:
            raise SchemaError(f"{label} sets npz without key.")
        values = _load_npz_array(base, raw.npz, raw.key)
    else:
        values = np.asarray(raw.inline)
    if raw.type == "vector3":
        values = np.asarray(values, dtype=float)
        if values.ndim != 2 or values.shape[1] != 3:
            raise SchemaError(f"{label} vector3 values must have shape (N, 3), got {values.shape}.")
    elif raw.type == "float":
        values = np.asarray(values, dtype=float).reshape(-1)
    else:
        values = np.asarray(values, dtype=int).reshape(-1)
    if values.size > MAX_INLINE and raw.inline is not None:
        raise SchemaError(f"{label} inline values exceed {MAX_INLINE}. Use NPZ.")
    return LoadedAttribute(raw.name, raw.domain, raw.type, raw.role, values)


def _load_object(base: Path, raw: Any) -> LoadedObject:
    transform = np.asarray(raw.transform.matrix, dtype=float)
    points = None
    faces = None
    correspondence = "none"
    geometry_space = None
    if raw.geometry is not None:
        geometry = raw.geometry
        geometry_space = geometry.space
        correspondence = geometry.correspondence
        _exclusive(geometry.points, geometry.points_npz, what=f"{raw.name} points")
        if geometry.points is not None:
            points = _as_points(np.asarray(geometry.points, dtype=float), what=f"{raw.name} points")
        else:
            if not geometry.points_key:
                raise SchemaError(f"{raw.name} points_npz requires points_key.")
            points = _as_points(
                _load_npz_array(base, geometry.points_npz, geometry.points_key),
                what=f"{raw.name} points",
            )
        if points.shape[0] != geometry.point_count:
            raise SchemaError(
                f"{raw.name} point_count is {geometry.point_count} but the points array has {points.shape[0]}.",
                hint="point_count must match the array. ParityForge does not drop extra points.",
            )
        has_inline_faces = geometry.face_counts is not None or geometry.face_indices is not None
        has_npz_faces = geometry.faces_npz is not None
        if has_inline_faces and has_npz_faces:
            raise SchemaError(f"{raw.name} sets both inline faces and faces_npz.")
        if has_inline_faces:
            if geometry.face_counts is None or geometry.face_indices is None:
                raise SchemaError(f"{raw.name} faces need both face_counts and face_indices.")
            faces = _decode_faces(
                np.asarray(geometry.face_counts),
                np.asarray(geometry.face_indices),
                what=raw.name,
            )
        elif has_npz_faces:
            if not geometry.faces_counts_key or not geometry.faces_indices_key:
                raise SchemaError(f"{raw.name} faces_npz requires faces_counts_key and faces_indices_key.")
            faces = _decode_faces(
                _load_npz_array(base, geometry.faces_npz, geometry.faces_counts_key),
                _load_npz_array(base, geometry.faces_npz, geometry.faces_indices_key),
                what=raw.name,
            )
        if faces is not None and points is not None:
            limit = points.shape[0]
            for face in faces:
                if any(index < 0 or index >= limit for index in face):
                    raise SchemaError(f"{raw.name} has a face index outside 0..{limit - 1}.")

    instance_positions = None
    instance_ids = None
    instance_space = None
    instance_count = None
    instance_correspondence = "none"
    prototype = None
    if raw.instances is not None:
        instances = raw.instances
        instance_space = instances.space
        instance_count = instances.count
        instance_correspondence = instances.correspondence
        prototype = instances.prototype
        has_positions = instances.positions is not None or instances.positions_npz is not None
        if not has_positions:
            raise SchemaError(
                f"{raw.name} instances.count is {instances.count} but positions are missing.",
                hint="Instance positions are required. A count alone is not a match.",
            )
        _exclusive(instances.positions, instances.positions_npz, what=f"{raw.name} instance positions")
        if instances.positions is not None:
            instance_positions = _as_points(
                np.asarray(instances.positions, dtype=float),
                what=f"{raw.name} instance positions",
            )
        else:
            if not instances.positions_key:
                raise SchemaError(f"{raw.name} positions_npz requires positions_key.")
            instance_positions = _as_points(
                _load_npz_array(base, instances.positions_npz, instances.positions_key),
                what=f"{raw.name} instance positions",
            )
        if instance_positions.shape[0] != instances.count:
            raise SchemaError(
                f"{raw.name} instances.count is {instances.count} but positions has "
                f"{instance_positions.shape[0]} rows.",
                hint="The count must match the position array.",
            )
        if instances.ids is not None and instances.ids_npz is not None:
            raise SchemaError(f"{raw.name} instance ids set both inline data and an NPZ reference.")
        if instances.ids is not None:
            instance_ids = np.asarray(instances.ids, dtype=int).reshape(-1)
        elif instances.ids_npz is not None:
            if not instances.ids_key:
                raise SchemaError(f"{raw.name} ids_npz requires ids_key.")
            instance_ids = np.asarray(_load_npz_array(base, instances.ids_npz, instances.ids_key)).reshape(-1)
        if instance_ids is not None and len(instance_ids) != instances.count:
            raise SchemaError(
                f"{raw.name} instance id count {len(instance_ids)} does not match instances.count {instances.count}."
            )

    attributes = [_load_attribute(base, attr) for attr in raw.attributes]
    return LoadedObject(
        name=raw.name,
        path=raw.path,
        type=raw.type,
        transform=transform,
        geometry_space=geometry_space,
        points=points,
        faces=faces,
        correspondence=correspondence,
        instance_space=instance_space,
        instance_positions=instance_positions,
        instance_ids=instance_ids,
        instance_correspondence=instance_correspondence,
        instance_prototype=prototype,
        instance_count=instance_count,
        attributes=attributes,
    )


def load_snapshot(path: Path, *, check_hash: bool = True) -> LoadedSnapshot:
    path = Path(path)
    if not path.is_file():
        raise SchemaError(
            f"Snapshot not found: {path}",
            hint="Pass the .snapshot.json file, not the NPZ sidecar.",
        )
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SchemaError(
            f"Malformed JSON in {path}: line {exc.lineno} column {exc.colno}: {exc.msg}.",
            hint="The snapshot metadata is JSON. Large arrays belong in a sibling NPZ file.",
        ) from exc
    document = migrate(raw)
    try:
        model = Snapshot.model_validate(document)
    except ValidationError as exc:
        raise SchemaError(_format_validation(exc)) from exc
    check_basis(model.identity)
    if check_hash:
        expected = metadata_sha256(document)
        if model.hashes.metadata_sha256 != expected:
            raise SchemaError(
                f"Metadata hash mismatch for {path.name}.",
                hint=(
                    f"Declared {model.hashes.metadata_sha256}, recomputed {expected}. "
                    "The file was edited after it was sealed, or it was not written by ParityForge. "
                    "Rebuild it with the snapshot writer. Validation will not ignore a bad hash."
                ),
            )
        base = path.parent
        for filename, digest in model.hashes.arrays.items():
            array_path = _safe_relative(base, filename)
            if not array_path.is_file():
                raise SchemaError(
                    f"Hashed array file {filename} is missing.",
                    hint=f"Expected it beside {path.name}.",
                )
            actual = _sha256_file(array_path)
            if actual != digest:
                raise SchemaError(
                    f"Array hash mismatch for {filename}.",
                    hint=f"Declared {digest}, recomputed {actual}.",
                )
    objects = [_load_object(path.parent, obj) for obj in model.objects]
    names = [obj.name for obj in objects]
    if len(names) != len(set(names)):
        raise SchemaError(
            f"Duplicate object names in {path.name}: {names}.",
            hint="Object names are the pairing key. Make them unique.",
        )
    return LoadedSnapshot(model=model, path=path, objects=objects)


def save_snapshot(
    path: Path,
    document: dict[str, Any],
    arrays: dict[str, dict[str, Array]] | None = None,
) -> dict[str, Any]:
    """Write pretty JSON and compressed NPZ sidecars. Returns the sealed document."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    sealed = migrate(dict(document))
    sealed.pop("hashes", None)
    array_hashes: dict[str, str] = {}
    for filename, payload in (arrays or {}).items():
        target = _safe_relative(path.parent, filename)
        np.savez_compressed(target, **{key: np.asarray(value) for key, value in payload.items()})
        array_hashes[filename] = _sha256_file(target)
    sealed["hashes"] = {
        "algorithm": "sha256",
        "metadata_sha256": metadata_sha256(sealed),
        "arrays": array_hashes,
    }
    # Validate before publishing the file so we never write a snapshot we cannot read.
    try:
        model = Snapshot.model_validate(sealed)
    except ValidationError as exc:
        raise SchemaError(_format_validation(exc)) from exc
    check_basis(model.identity)
    path.write_text(json.dumps(sealed, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    load_snapshot(path)
    return sealed
