"""parityforge command line."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .compare import compare_loaded
from .config import default_config, load_config
from .doctor import diagnose, format_doctor
from .errors import ParityError
from .report import write_report
from .snapshot_io import load_snapshot
from .suite import run_suite


def _build() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="parityforge", description="Compare evaluated procedural geometry.")
    parser.add_argument("--version", action="version", version=f"parityforge {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    validate = sub.add_parser("validate", help="Validate a snapshot JSON file and its NPZ hashes")
    validate.add_argument("snapshot")

    compare = sub.add_parser("compare", help="Compare two snapshots offline")
    compare.add_argument("baseline")
    compare.add_argument("candidate")
    compare.add_argument("--config", default=None, help="parityforge.toml with intent and tolerances")
    compare.add_argument("--out", required=True, help="Directory for report.json and report.html")

    suite = sub.add_parser("suite", help="Run a YAML suite of comparisons")
    suite.add_argument("suite")
    suite.add_argument("--out", required=True, help="Directory for suite reports")

    sub.add_parser("doctor", help="Report offline stack and optional Blender/Houdini executables")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build()
    args = parser.parse_args(argv)
    try:
        if args.command == "validate":
            loaded = load_snapshot(Path(args.snapshot))
            identity = loaded.model.identity
            print(
                f"valid {args.snapshot}: schema {loaded.model.schema_version}, "
                f"{identity.source_app} {identity.source_version}, {len(loaded.objects)} object(s)"
            )
            return 0
        if args.command == "compare":
            if args.config:
                config = load_config(Path(args.config))
                source = args.config
            else:
                config = default_config("identity")
                source = "built-in identity defaults"
                print("No --config file. Using built-in identity tolerances.", file=sys.stderr)
            report = compare_loaded(
                load_snapshot(Path(args.baseline)),
                load_snapshot(Path(args.candidate)),
                config,
                config_source=source,
            )
            json_path, html_path = write_report(report, Path(args.out))
            print(report["summary"])
            print(f"Wrote {json_path}")
            print(f"Wrote {html_path}")
            return {"PASS": 0, "FAIL": 1, "INCONCLUSIVE": 2}.get(report["overall"], 2)
        if args.command == "suite":
            suite_report = run_suite(Path(args.suite), Path(args.out))
            for case in suite_report["cases"]:
                print(f"{case['id']}: {case['overall']} {case['equality_claim']}")
            if suite_report["failures"]:
                print("Expectation failures:", file=sys.stderr)
                for failure in suite_report["failures"]:
                    print(f"  {failure}", file=sys.stderr)
                return 1
            print(f"Wrote {Path(args.out) / 'index.html'}")
            return 0
        if args.command == "doctor":
            report = diagnose()
            sys.stdout.write(format_doctor(report))
            return 0 if report["offline"]["status"] == "available" else 1
    except ParityError as exc:
        print(exc, file=sys.stderr)
        return 3
    print(f"Unknown command {args.command}", file=sys.stderr)
    return 3
