# Contributing

ParityForge measures evaluated geometry. A change that makes a mismatched cloud pass by aligning it, dropping an attribute, or treating a missing metric as zero is a bug.

## Setup

```bash
python -m pip install -e ".[dev]"
python -m pytest
ruff check src tests tools scripts
```

Python 3.11 or newer. Tests must pass without Blender and without Houdini. Live tests skip when those executables are absent; do not delete the skip and do not stub a passing live result.

## Snapshots

* Bump behaviour by adding a schema version and a migration in `parityforge.migrations`. Do not silently accept an unknown version.
* Keep large arrays in NPZ. The inline cap is intentional.
* New metrics need a tolerance with a unit and a minimum sample count, a rationale string, and a test for pass, fail, and the not-evaluated path.
* Distributional metrics must not be described as vertex identity in the summary.

## Hosts

Capture code that touches `bpy` or `hou` stays behind an import inside `main` or a function that receives the module. Add the command to `hosts/invocation.py` and to the README together. If you document a flag, argparse has to accept it.

Unreal work belongs against `docs/unreal_v0.2.md`. Do not add fabricated Editor output to the fixtures.

## Fixtures

Regenerate with `python tools/build_fixtures.py` after changing `authoring.py`. The NodeBridge report text in `fixtures/nodebridge_scatter/` is a copy of NodeBridge's published scatter report. Replace it only when the audited commit changes, and update `link.json`.
