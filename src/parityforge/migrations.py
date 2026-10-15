"""Versioned snapshot migrations.

Production loading accepts schema 1.0.0 only. A migration runs solely when it
is registered for the document's current ``schema_version``. Unknown versions
are rejected with the supported version named in the error. There is no silent
rewrite of a newer or older file.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .errors import SchemaError

CURRENT_SCHEMA = "1.0.0"
Migration = Callable[[dict[str, Any]], dict[str, Any]]

# Empty on purpose: 1.0.0 is the first shipped schema. Tests register a
# temporary 0.9.0 -> 1.0.0 step to prove the chain refuses cycles and
# unregistered versions.
PRODUCTION_MIGRATIONS: dict[str, Migration] = {}


def migrate(
    document: dict[str, Any],
    *,
    registry: dict[str, Migration] | None = None,
    target: str = CURRENT_SCHEMA,
) -> dict[str, Any]:
    if not isinstance(document, dict):
        raise SchemaError(
            "Snapshot root must be a JSON object.",
            hint="See docs/schema.md for schema 1.0.0.",
        )
    version = document.get("schema_version")
    if not isinstance(version, str) or not version:
        raise SchemaError(
            "Missing schema_version.",
            hint=f'Add "schema_version": "{CURRENT_SCHEMA}". Supported snapshot schema: {CURRENT_SCHEMA}.',
        )
    steps = PRODUCTION_MIGRATIONS if registry is None else registry
    seen: list[str] = []
    current = dict(document)
    while current.get("schema_version") != target:
        key = current.get("schema_version")
        if not isinstance(key, str) or key not in steps:
            supported = ", ".join([target, *sorted(steps)])
            raise SchemaError(
                f"Unsupported schema_version {key!r}. This build reads {target} "
                f"and will not guess a migration.",
                hint=f"Supported versions reachable here: {supported}. See docs/schema.md.",
            )
        if key in seen:
            raise SchemaError(f"Snapshot migration cycle detected at schema_version {key!r}.")
        seen.append(key)
        if len(seen) > 8:
            raise SchemaError("Snapshot migration exceeded 8 steps. Refusing to continue.")
        current = steps[key](current)
        if not isinstance(current, dict) or not isinstance(current.get("schema_version"), str):
            raise SchemaError(f"Migration from {key!r} did not return a document with schema_version.")
    return current
