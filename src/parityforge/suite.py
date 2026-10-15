"""Run a YAML suite of snapshot comparisons."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .compare import compare_loaded
from .config import load_config
from .errors import SchemaError
from .nodebridge_link import load_link
from .report import write_json, write_report
from .snapshot_io import load_snapshot


def load_suite(path: Path) -> dict[str, Any]:
    path = Path(path)
    if not path.is_file():
        raise SchemaError(f"Suite file not found: {path}", hint="Pass a YAML file such as fixtures/suite.yaml.")
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise SchemaError(f"Could not parse suite {path}: {exc}") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("cases"), list):
        raise SchemaError(
            "Suite YAML needs a cases list.",
            hint="See fixtures/suite.yaml.",
        )
    if payload.get("schema_version") != "1.0.0":
        raise SchemaError(
            f"Unsupported suite schema_version {payload.get('schema_version')!r}.",
            hint='Use schema_version: "1.0.0".',
        )
    return payload


def _expect(case_id: str, report: dict[str, Any], expect: dict[str, Any]) -> list[str]:
    failures = []
    if "overall" in expect and report["overall"] != expect["overall"]:
        failures.append(f"{case_id}: overall is {report['overall']}, expected {expect['overall']}")
    if "equality_claim" in expect and report["equality_claim"] != expect["equality_claim"]:
        failures.append(
            f"{case_id}: equality_claim is {report['equality_claim']}, expected {expect['equality_claim']}"
        )
    for label in expect.get("labels") or []:
        if label not in report["labels"]:
            failures.append(f"{case_id}: missing label {label}")
    wanted = expect.get("metrics") or {}
    by_suffix: dict[str, list[str]] = {}
    for metric in report["metrics"]:
        by_suffix.setdefault(metric["id"].split(".")[-1], []).append(metric["status"])
        by_suffix.setdefault(metric["id"], []).append(metric["status"])
    for metric_id, status in wanted.items():
        found = by_suffix.get(metric_id)
        if not found:
            failures.append(f"{case_id}: metric {metric_id} was not produced")
        elif status not in found:
            failures.append(f"{case_id}: metric {metric_id} statuses {found}, expected {status}")
    return failures


def run_suite(path: Path, out_dir: Path) -> dict[str, Any]:
    path = Path(path)
    payload = load_suite(path)
    out_dir.mkdir(parents=True, exist_ok=True)
    cases_out = []
    expectation_failures: list[str] = []
    for case in payload["cases"]:
        case_id = case["id"]
        baseline_path = (path.parent / case["baseline"]).resolve()
        candidate_path = (path.parent / case["candidate"]).resolve()
        config_path = (path.parent / case["config"]).resolve()
        config = load_config(config_path)
        report = compare_loaded(
            load_snapshot(baseline_path),
            load_snapshot(candidate_path),
            config,
            config_source=str(config_path),
        )
        if case.get("nodebridge_link"):
            report["nodebridge"] = load_link((path.parent / case["nodebridge_link"]).resolve())
        case_dir = out_dir / case_id
        write_report(report, case_dir)
        failures = _expect(case_id, report, case.get("expect") or {})
        expectation_failures.extend(failures)
        cases_out.append(
            {
                "id": case_id,
                "overall": report["overall"],
                "equality_claim": report["equality_claim"],
                "labels": report["labels"],
                "summary": report["summary"],
                "report_html": f"{case_id}/report.html",
                "expectation_failures": failures,
            }
        )
    suite_report = {
        "schema_version": "1.0.0",
        "suite": str(path),
        "passed": not expectation_failures,
        "failures": expectation_failures,
        "cases": cases_out,
    }
    write_json(suite_report, out_dir / "suite.json")
    items = []
    for case in cases_out:
        flag = "ok" if not case["expectation_failures"] else "expectation mismatch"
        items.append(
            "<li>"
            f"<a href=\"{case['report_html']}\"><code>{case['id']}</code></a> "
            f"{case['overall']} · {case['equality_claim']} · {flag}"
            f"<br>{case['summary']}"
            "</li>"
        )
    page = (
        "<!DOCTYPE html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<title>ParityForge suite</title>"
        "<style>body{font:16px/1.45 Palatino,Georgia,serif;background:#f3efe6;color:#1d1a16;"
        "max-width:900px;margin:32px auto;padding:0 16px}code{font-family:ui-monospace,Menlo,monospace}"
        "a{color:#0f4c81}</style></head><body>"
        f"<h1>ParityForge suite</h1><p>Expectations {'held' if suite_report['passed'] else 'failed'}.</p>"
        f"<ul>{''.join(items)}</ul></body></html>"
    )
    (out_dir / "index.html").write_text(page, encoding="utf-8")
    return suite_report
