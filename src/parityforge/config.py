"""Comparison tolerances, gates, and TOML loading."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from .errors import SchemaError
from .models import CompareConfig, ToleranceSpec

# A priori thresholds. Distribution tolerances are sized for a multi-meter
# sampling domain, not for vertex identity. Identity tolerances are millimeters
# and a hundredth of a degree. See docs/architecture.md.
DEFAULT_TOLERANCES: dict[str, ToleranceSpec] = {
    "centroid": ToleranceSpec(absolute=1e-3, relative=0.0, unit="meter", minimum_samples=1),
    "bounds": ToleranceSpec(absolute=1e-3, relative=0.0, unit="meter", minimum_samples=1),
    "extents": ToleranceSpec(absolute=1e-3, relative=0.0, unit="meter", minimum_samples=1),
    "surface_area": ToleranceSpec(absolute=1e-3, relative=1e-4, unit="meter^2", minimum_samples=1),
    "vertex_position": ToleranceSpec(absolute=1e-3, relative=0.0, unit="meter", minimum_samples=1),
    "hausdorff": ToleranceSpec(absolute=1e-3, relative=0.0, unit="meter", minimum_samples=1),
    "cross_nn_p99": ToleranceSpec(absolute=1e-3, relative=0.0, unit="meter", minimum_samples=1),
    "transform_translation": ToleranceSpec(absolute=1e-3, relative=0.0, unit="meter", minimum_samples=1),
    "transform_rotation": ToleranceSpec(absolute=1e-2, relative=0.0, unit="degree", minimum_samples=1),
    "transform_scale": ToleranceSpec(absolute=1e-4, relative=0.0, unit="1", minimum_samples=1),
    "parameters": ToleranceSpec(absolute=0.0, relative=0.0, unit="1", minimum_samples=1),
    "attribute_value": ToleranceSpec(absolute=1e-4, relative=0.0, unit="1", minimum_samples=1),
    "density_total_variation": ToleranceSpec(absolute=0.12, relative=0.0, unit="1", minimum_samples=200),
    "nn_distance_wasserstein": ToleranceSpec(
        absolute=0.05, relative=0.0, unit="meter", minimum_samples=200
    ),
}

IDENTITY_GATES = [
    "object_count",
    "point_count",
    "face_count",
    "instance_count",
    "instance_ids",
    "seed",
    "parameters",
    "attribute_schema",
    "attribute_values",
    "topology",
    "centroid",
    "bounds",
    "extents",
    "surface_area",
    "vertex_position",
    "transform",
]

DISTRIBUTION_GATES = [
    "object_count",
    "point_count",
    "instance_count",
    "seed",
    "parameters",
    "attribute_schema",
    "centroid",
    "bounds",
    "density_total_variation",
    "nn_distance_wasserstein",
]


def default_config(intent: str = "identity") -> CompareConfig:
    if intent not in {"identity", "distribution"}:
        raise SchemaError(
            f"Unknown comparison intent {intent!r}.",
            hint="Use identity or distribution.",
        )
    return CompareConfig(intent=intent, tolerances=dict(DEFAULT_TOLERANCES))


def gates_for(config: CompareConfig) -> list[str]:
    if config.gates:
        return list(config.gates)
    if config.intent == "distribution":
        return list(DISTRIBUTION_GATES)
    return list(IDENTITY_GATES)


def _tolerances_from_table(table: dict[str, Any]) -> dict[str, ToleranceSpec]:
    merged = dict(DEFAULT_TOLERANCES)
    for name, raw in table.items():
        if not isinstance(raw, dict):
            raise SchemaError(
                f"tolerances.{name} must be a table with absolute/relative/unit/minimum_samples."
            )
        base = merged.get(name, ToleranceSpec())
        data = base.model_dump()
        unknown = set(raw) - set(data)
        if unknown:
            raise SchemaError(
                f"tolerances.{name} has unknown keys: {sorted(unknown)}.",
                hint="Allowed keys: absolute, relative, unit, minimum_samples.",
            )
        data.update(raw)
        merged[name] = ToleranceSpec.model_validate(data)
    return merged


def load_config(path: Path) -> CompareConfig:
    path = Path(path)
    if not path.is_file():
        raise SchemaError(
            f"Config file not found: {path}",
            hint="Pass --config pointing at a parityforge.toml. See docs/schema.md.",
        )
    try:
        payload = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise SchemaError(
            f"Could not parse {path}: {exc}",
            hint="parityforge.toml is TOML. Check quotes and tables.",
        ) from exc
    if not isinstance(payload, dict):
        raise SchemaError(f"{path} did not contain a TOML table.")
    version = payload.get("schema_version", "1.0.0")
    if version != "1.0.0":
        raise SchemaError(
            f"Unsupported config schema_version {version!r}.",
            hint='Use schema_version = "1.0.0".',
        )
    intent = payload.get("intent", "identity")
    gate_table = payload.get("gates")
    gates: list[str] | None = None
    if gate_table is not None:
        if not isinstance(gate_table, dict) or "ids" not in gate_table:
            raise SchemaError(
                "gates must be a table with an ids array.",
                hint='Example: [gates]\nids = ["centroid", "bounds"]',
            )
        gates = list(gate_table["ids"])
        if any(not isinstance(item, str) for item in gates):
            raise SchemaError("gates.ids must be a list of metric id strings.")
    tolerances = _tolerances_from_table(payload.get("tolerances") or {})
    try:
        return CompareConfig(
            schema_version="1.0.0",
            intent=intent,
            gates=gates,
            tolerances=tolerances,
        )
    except Exception as exc:
        raise SchemaError(
            f"Invalid comparison config {path}: {exc}",
            hint="intent must be identity or distribution.",
        ) from exc
