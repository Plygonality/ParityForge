"""JSON and self-contained HTML reports."""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any


def write_json(report: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _pill(status: str) -> str:
    return f'<span class="pill {html.escape(status)}">{html.escape(status)}</span>'


def _fmt(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.6g}"
    if isinstance(value, list | dict):
        return html.escape(json.dumps(value, ensure_ascii=False))
    if value is None:
        return ""
    return html.escape(str(value))


def render_html(report: dict[str, Any]) -> str:
    rows = []
    for metric in report["metrics"]:
        tolerance = metric.get("tolerance") or {}
        tol_text = ""
        if tolerance:
            tol_text = (
                f"abs {tolerance.get('absolute')} + rel {tolerance.get('relative')}"
                f" {tolerance.get('unit', '')}; min samples {tolerance.get('minimum_samples')}"
            )
            if "limit" in tolerance:
                tol_text += f"; limit {tolerance['limit']}"
        gate = "yes" if metric.get("gated") else "no"
        rows.append(
            "<tr>"
            f"<td><code>{html.escape(metric['id'])}</code></td>"
            f"<td>{_pill(metric['status'])}</td>"
            f"<td>{html.escape(metric['kind'])}</td>"
            f"<td>{gate}</td>"
            f"<td>{_fmt(metric.get('value'))}</td>"
            f"<td>{html.escape(tol_text)}</td>"
            f"<td>{html.escape(metric['rationale'])}</td>"
            "</tr>"
        )
    warnings = report.get("warnings") or []
    warning_html = "".join(f"<li>{html.escape(str(item))}</li>" for item in warnings) or "<li>None.</li>"
    notes = "".join(f"<li>{html.escape(str(item))}</li>" for item in report.get("notes", []))
    labels = ", ".join(report.get("labels") or []) or "none"
    thumbnails = []
    image = next((item for item in report["metrics"] if item["id"] == "image"), None)
    if image:
        for side in ("baseline", "candidate"):
            thumb = (image.get("value") or {}).get(f"thumbnail_{side}")
            if thumb:
                thumbnails.append(
                    f"<li>{html.escape(side)}: <a href=\"{html.escape(str(thumb))}\">{html.escape(str(thumb))}</a></li>"
                )
    thumb_html = "".join(thumbnails) or "<li>No thumbnail was declared.</li>"
    nodebridge = report.get("nodebridge")
    node_html = ""
    if nodebridge:
        node_html = (
            "<section><h2>NodeBridge link</h2>"
            f"<p>Fidelity for {html.escape(str(nodebridge.get('operation', '')))}: "
            f"<strong>{html.escape(str(nodebridge.get('fidelity_class', '')))}</strong>. "
            "This is the translation report's class. It is not a measured geometry result.</p>"
            f"<pre>{html.escape(json.dumps(nodebridge, indent=2))}</pre></section>"
        )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>ParityForge {html.escape(report['overall'])}</title>
<style>
  :root {{ color-scheme: light; }}
  body {{ margin: 0; background: #f3efe6; color: #1d1a16; font: 16px/1.5 "Iowan Old Style", Palatino, Georgia, serif; }}
  main {{ max-width: 1100px; margin: 0 auto; padding: 32px 20px 64px; }}
  h1 {{ font-size: 34px; line-height: 1.1; margin: 0 0 8px; }}
  h2 {{ font-size: 20px; margin: 28px 0 8px; }}
  p {{ margin: 8px 0; }}
  code, pre {{ font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 13px; }}
  pre {{ white-space: pre-wrap; background: #fff; border: 1px solid #ddd4c6; padding: 12px; }}
  table {{ width: 100%; border-collapse: collapse; background: #fff; }}
  th, td {{ border-bottom: 1px solid #e4dccb; text-align: left; vertical-align: top; padding: 8px; font-size: 13px; }}
  th {{ font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-weight: 600; }}
  .summary {{ background: #fff; border-left: 6px solid #1d1a16; padding: 12px 16px; }}
  .pill {{ display: inline-block; padding: 1px 8px; border-radius: 999px;
           font-family: ui-monospace, Menlo, Consolas, monospace; font-size: 12px; }}
  .PASS {{ background: #d9efe4; color: #0d5c3d; }}
  .FAIL {{ background: #f8d6d2; color: #8d1d18; }}
  .INCONCLUSIVE {{ background: #f8e7c4; color: #7a4b00; }}
  .UNSUPPORTED {{ background: #e1e5ea; color: #243140; }}
  .NOT_EVALUATED {{ background: #ece7df; color: #4d473f; }}
  a {{ color: #0f4c81; }}
</style>
</head>
<body>
<main>
  <p>ParityForge {html.escape(str(report.get("parityforge", "")))}</p>
  <h1>{_pill(report["overall"])} {html.escape(report["equality_claim"])}</h1>
  <p>Intent <code>{html.escape(report["intent"])}</code> · labels <code>{html.escape(labels)}</code></p>
  <section class="summary"><p>{html.escape(report["summary"])}</p></section>
  <h2>Notes</h2>
  <ul>{notes}</ul>
  <h2>Warnings</h2>
  <ul>{warning_html}</ul>
  <h2>Metrics</h2>
  <table>
    <thead><tr><th>Metric</th><th>Status</th><th>Kind</th><th>Gate</th><th>Value</th><th>Tolerance</th><th>Rationale</th></tr></thead>
    <tbody>
    {''.join(rows)}
    </tbody>
  </table>
  <h2>Thumbnails</h2>
  <ul>{thumb_html}</ul>
  {node_html}
</main>
</body>
</html>
"""


def write_report(report: dict[str, Any], out_dir: Path) -> tuple[Path, Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "report.json"
    html_path = out_dir / "report.html"
    write_json(report, json_path)
    html_path.write_text(render_html(report), encoding="utf-8")
    return json_path, html_path
