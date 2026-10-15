"""Report optional DCC executables without inventing ones that are absent."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from . import __version__
from .hosts.invocation import BLENDER_CAPTURE_EXAMPLE, HOUDINI_CAPTURE_EXAMPLE


def _import_versions() -> dict[str, Any]:
    try:
        import numpy
        import pydantic
        import scipy
    except ImportError as exc:
        return {"status": "unavailable", "detail": str(exc)}
    return {
        "status": "available",
        "numpy": numpy.__version__,
        "scipy": scipy.__version__,
        "pydantic": pydantic.__version__,
    }


def _run_version(command: list[str], timeout: float = 30) -> tuple[bool, str]:
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)
    text = (completed.stdout or "") + (completed.stderr or "")
    if completed.returncode != 0 and not text.strip():
        return False, f"exit {completed.returncode}"
    return completed.returncode == 0, text.strip()


def _probe_blender() -> dict[str, Any]:
    env_path = os.environ.get("PARITYFORGE_BLENDER")
    found = env_path or shutil.which("blender")
    result: dict[str, Any] = {
        "status": "unavailable",
        "path": found,
        "version": None,
        "capture": BLENDER_CAPTURE_EXAMPLE,
    }
    if not found:
        result["detail"] = "Not found on PATH and PARITYFORGE_BLENDER is unset."
        return result
    if not Path(found).is_file() and shutil.which(found) is None:
        result["detail"] = f"PARITYFORGE_BLENDER={found} is not an executable file."
        result["path"] = found
        return result
    ok, text = _run_version([found, "--version"])
    result["probe"] = text.splitlines()[:4]
    if not ok:
        result["status"] = "found_but_unusable"
        result["detail"] = "The executable was found but `blender --version` did not succeed."
        return result
    result["status"] = "available"
    result["version"] = text.splitlines()[0] if text else "unknown"
    result["detail"] = "Version probe succeeded."
    return result


def _hython_candidates() -> list[str]:
    found = []
    env_path = os.environ.get("PARITYFORGE_HYTHON")
    if env_path:
        found.append(env_path)
    which = shutil.which("hython")
    if which and which not in found:
        found.append(which)
    hfs = os.environ.get("HFS")
    if hfs:
        candidate = str(Path(hfs) / "bin" / "hython")
        if candidate not in found:
            found.append(candidate)
    return found


def _probe_houdini() -> dict[str, Any]:
    result: dict[str, Any] = {
        "status": "unavailable",
        "path": None,
        "version": None,
        "capture": HOUDINI_CAPTURE_EXAMPLE,
        "lane": "NOT_RUN",
    }
    candidates = _hython_candidates()
    if not candidates:
        result["detail"] = "hython was not found. PARITYFORGE_HYTHON and HFS are unset, and hython is not on PATH."
        return result
    for candidate in candidates:
        if not Path(candidate).is_file():
            result["path"] = candidate
            result["status"] = "found_but_unusable"
            result["detail"] = f"{candidate} is not a file."
            continue
        ok, text = _run_version([candidate, "-c", "import hou; print(hou.applicationVersionString())"])
        result["path"] = candidate
        result["probe"] = text.splitlines()[:8]
        if ok and text:
            result["status"] = "available"
            result["version"] = text.splitlines()[-1]
            result["lane"] = "available"
            result["detail"] = "hython imported hou and printed a version."
            return result
        result["status"] = "found_but_unusable"
        result["detail"] = "hython was found but did not import hou. A missing license leaves this lane NOT_RUN."
        result["lane"] = "NOT_RUN"
    return result


def diagnose() -> dict[str, Any]:
    offline = _import_versions()
    return {
        "parityforge": __version__,
        "offline": offline,
        "blender": _probe_blender(),
        "houdini": _probe_houdini(),
        "unreal": {
            "status": "deferred",
            "lane": "NOT_RUN",
            "detail": "No Unreal adapter is shipped in v0.1. Editor Python was not probed. See docs/unreal_v0.2.md.",
        },
    }


def format_doctor(report: dict[str, Any]) -> str:
    offline = report["offline"]
    blender = report["blender"]
    houdini = report["houdini"]
    lines = [
        f"ParityForge {report['parityforge']} doctor",
        "",
    ]
    if offline["status"] == "available":
        lines.append(
            "offline comparison: available "
            f"(numpy {offline['numpy']}, scipy {offline['scipy']}, pydantic {offline['pydantic']})"
        )
    else:
        lines.append(f"offline comparison: unavailable ({offline.get('detail')})")
    lines.append(f"blender: {blender['status']}")
    lines.append(f"  path: {blender.get('path') or 'not found'}")
    lines.append(f"  version: {blender.get('version') or 'not available'}")
    lines.append(f"  {blender.get('detail', '')}")
    lines.append(f"  capture: {blender['capture']}")
    lines.append(f"houdini: {houdini['status']}")
    lines.append(f"  path: {houdini.get('path') or 'not found'}")
    lines.append(f"  version: {houdini.get('version') or 'not available'}")
    lines.append(f"  lane: {houdini.get('lane')}")
    lines.append(f"  {houdini.get('detail', '')}")
    lines.append(f"  capture: {houdini['capture']}")
    lines.append(f"unreal: {report['unreal']['status']}")
    lines.append(f"  lane: {report['unreal']['lane']}")
    lines.append(f"  {report['unreal']['detail']}")
    return "\n".join(lines) + "\n"
