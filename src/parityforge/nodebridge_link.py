"""Read a NodeBridge translation report. ParityForge does not compile graphs."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .errors import SchemaError

_HEADER = "NodeBridge Translation Report"
_COUNT = re.compile(
    r"^[✓≈~✕]\s+(EXACT|EQUIVALENT|APPROXIMATE|UNSUPPORTED):\s+(\d+)\s*$",
    re.MULTILINE,
)
_OPERATION = re.compile(
    r"^\s+[✓≈~✕]\s+(EXACT|EQUIVALENT|APPROXIMATE|UNSUPPORTED)\s+(.+?)\s{2,}([A-Z][A-Z0-9_]*)\s+->\s+(.+?)\s*$"
)


def parse_translation_report(text: str) -> dict[str, Any]:
    if _HEADER not in text:
        raise SchemaError(
            "The file is not a NodeBridge translation report.",
            hint="Expected the header 'NodeBridge Translation Report' from NodeBridge's text report.",
        )
    counts = {name: int(value) for name, value in _COUNT.findall(text)}
    operations = []
    for line in text.splitlines():
        match = _OPERATION.match(line)
        if not match:
            continue
        operations.append(
            {
                "fidelity": match.group(1),
                "name": match.group(2).strip(),
                "kind": match.group(3),
                "implementation": match.group(4).strip(),
            }
        )
    if set(counts) != {"EXACT", "EQUIVALENT", "APPROXIMATE", "UNSUPPORTED"} or not operations:
        raise SchemaError(
            "Could not read fidelity counts and operations from the NodeBridge report.",
            hint="Use the text report NodeBridge writes (expected_report_*.txt), not a screenshot.",
        )
    return {
        "format": "nodebridge_text_report",
        "counts": counts,
        "operations": operations,
    }


def load_link(path: Path) -> dict[str, Any]:
    """Load a small JSON link next to a copied NodeBridge text report."""
    import json

    path = Path(path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SchemaError(f"Malformed NodeBridge link {path}: {exc}") from exc
    report_name = payload.get("translation_report")
    if not report_name:
        raise SchemaError(
            f"{path} is missing translation_report.",
            hint="Point translation_report at the NodeBridge text report.",
        )
    report_path = path.parent / report_name
    if not report_path.is_file():
        raise SchemaError(f"NodeBridge report not found: {report_path}")
    parsed = parse_translation_report(report_path.read_text(encoding="utf-8"))
    kind = payload.get("operation_kind", "SCATTER")
    matches = [op for op in parsed["operations"] if op["kind"] == kind]
    if not matches:
        raise SchemaError(
            f"NodeBridge report has no operation kind {kind!r}.",
            hint="Set operation_kind to a kind listed in the report, such as SCATTER.",
        )
    fidelity = matches[0]["fidelity"]
    return {
        "repository": payload.get("repository", "https://github.com/Plygonality/NodeBridge"),
        "audited_commit": payload.get("audited_commit", ""),
        "source_graph": payload.get("source_graph", ""),
        "translation_report": report_name,
        "operation_kind": kind,
        "operation_name": matches[0]["name"],
        "fidelity_class": fidelity,
        "fidelity_counts": parsed["counts"],
        "note": payload.get(
            "note",
            "Fidelity class is taken from the NodeBridge report. It is not a ParityForge measurement.",
        ),
    }
