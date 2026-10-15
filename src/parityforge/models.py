"""Snapshot and config models for schema 1.0.0."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .coordinates import validate_basis
from .errors import SchemaError

MAX_INLINE = 100_000


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CoordinateBasis(StrictModel):
    name: str
    handedness: Literal["right", "left"]
    up_axis: Literal["X", "Y", "Z"]
    forward_axis: str
    matrix_to_canonical: list[list[float]]

    @field_validator("matrix_to_canonical")
    @classmethod
    def _matrix_shape(cls, value: list[list[float]]) -> list[list[float]]:
        if len(value) != 3 or any(len(row) != 3 for row in value):
            raise ValueError("matrix_to_canonical must be 3x3")
        return value


class Units(StrictModel):
    length_unit: str
    meters_per_unit: float
    angle: Literal["radian", "degree"]

    @field_validator("meters_per_unit")
    @classmethod
    def _positive(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("meters_per_unit must be positive")
        return value


class TimeSample(StrictModel):
    frame: float
    fps: float
    seconds: float


class Identity(StrictModel):
    snapshot_id: str
    scene: str
    asset: str
    source_app: Literal["blender", "houdini", "unreal", "synthetic"]
    source_version: str
    time: TimeSample
    seed: int | None = None
    units: Units
    coordinate_basis: CoordinateBasis


class Transform(StrictModel):
    matrix: list[list[float]]

    @field_validator("matrix")
    @classmethod
    def _affine(cls, value: list[list[float]]) -> list[list[float]]:
        if len(value) != 4 or any(len(row) != 4 for row in value):
            raise ValueError("transform.matrix must be 4x4")
        return value


class Geometry(StrictModel):
    space: Literal["local", "world"] = "local"
    point_count: int = Field(ge=0)
    points: list[list[float]] | None = None
    points_npz: str | None = None
    points_key: str | None = None
    face_counts: list[int] | None = None
    face_indices: list[int] | None = None
    faces_npz: str | None = None
    faces_counts_key: str | None = None
    faces_indices_key: str | None = None
    correspondence: Literal["index", "none"] = "none"

    @field_validator("points")
    @classmethod
    def _inline_limit(cls, value: list[list[float]] | None) -> list[list[float]] | None:
        if value is not None and len(value) > MAX_INLINE:
            raise ValueError(
                f"inline points exceed {MAX_INLINE}. Store them in an NPZ array and set points_npz."
            )
        return value


class Instances(StrictModel):
    count: int = Field(ge=0)
    prototype: str | None = None
    space: Literal["local", "world"] = "world"
    positions: list[list[float]] | None = None
    positions_npz: str | None = None
    positions_key: str | None = None
    ids: list[int] | None = None
    ids_npz: str | None = None
    ids_key: str | None = None
    correspondence: Literal["index", "id", "none"] = "none"

    @field_validator("positions")
    @classmethod
    def _inline_limit(cls, value: list[list[float]] | None) -> list[list[float]] | None:
        if value is not None and len(value) > MAX_INLINE:
            raise ValueError(
                f"inline instance positions exceed {MAX_INLINE}. Store them in an NPZ array."
            )
        return value


class Attribute(StrictModel):
    name: str
    domain: Literal["point", "vertex", "edge", "face", "corner", "instance", "detail"]
    type: Literal["float", "int", "vector3"]
    role: Literal["scalar", "position", "direction", "color", "uv", "unknown"] = "scalar"
    inline: list[Any] | None = None
    npz: str | None = None
    key: str | None = None


class SceneObject(StrictModel):
    name: str
    path: str
    type: Literal["mesh", "points", "instances"]
    transform: Transform
    geometry: Geometry | None = None
    instances: Instances | None = None
    attributes: list[Attribute] = Field(default_factory=list)


class Execution(StrictModel):
    captured_at: str
    host_script: str
    command: str
    producer: str
    warnings: list[str] = Field(default_factory=list)
    thumbnail: str | None = None
    note: str = ""


class Hashes(StrictModel):
    algorithm: Literal["sha256"] = "sha256"
    metadata_sha256: str
    arrays: dict[str, str] = Field(default_factory=dict)


class Snapshot(StrictModel):
    schema_version: Literal["1.0.0"]
    identity: Identity
    parameters: dict[str, Any] = Field(default_factory=dict)
    objects: list[SceneObject]
    execution: Execution
    hashes: Hashes


class ToleranceSpec(StrictModel):
    absolute: float = 0.0
    relative: float = 0.0
    unit: str = ""
    minimum_samples: int = 1


class CompareConfig(StrictModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    intent: Literal["identity", "distribution"] = "identity"
    gates: list[str] | None = None
    tolerances: dict[str, ToleranceSpec] = Field(default_factory=dict)


def check_basis(identity: Identity) -> None:
    basis = identity.coordinate_basis
    try:
        validate_basis(
            name=basis.name,
            handedness=basis.handedness,
            up_axis=basis.up_axis,
            forward_axis=basis.forward_axis,
            matrix_to_canonical=basis.matrix_to_canonical,
        )
    except SchemaError:
        raise
    except ValueError as exc:
        raise SchemaError(str(exc)) from exc
