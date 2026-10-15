# Snapshot schema 1.0.0

A snapshot is a JSON object plus optional NPZ sidecars in the same directory. NPZ paths are filenames, not `../` paths.

## Required shape

```json
{
  "schema_version": "1.0.0",
  "identity": {
    "snapshot_id": "plane-blender-match",
    "scene": "PlaneScene",
    "asset": "Plane",
    "source_app": "blender",
    "source_version": "fixture",
    "time": {"frame": 1, "fps": 24, "seconds": 0.0},
    "seed": null,
    "units": {"length_unit": "meter", "meters_per_unit": 1.0, "angle": "radian"},
    "coordinate_basis": {
      "name": "blender",
      "handedness": "right",
      "up_axis": "Z",
      "forward_axis": "-Y",
      "matrix_to_canonical": [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
    }
  },
  "parameters": {},
  "objects": [],
  "execution": {
    "captured_at": "2026-10-15T00:00:00Z",
    "host_script": "scripts/capture_blender.py",
    "command": "python tools/build_fixtures.py",
    "producer": "parityforge.authoring",
    "warnings": [],
    "note": ""
  },
  "hashes": {
    "algorithm": "sha256",
    "metadata_sha256": "<hex>",
    "arrays": {}
  }
}
```

`source_app` is `blender`, `houdini`, `unreal`, or `synthetic`.

## Geometry

`geometry.space` is `local` or `world`. `point_count` must equal the array length. Faces are `face_counts` plus a flat `face_indices` list, or the same arrays inside `faces_npz`. `correspondence` is `index` or `none`. Index is opt-in. Capture scripts write `none` because a live export does not know that vertex `i` is the same element in another DCC.

Inline point arrays over 100,000 rows are rejected. Use `points_npz` and `points_key`.

## Instances

`instances.count` must match `positions`. Positions may be inline or `positions_npz`. Ids are optional. Missing ids are `NOT_EVALUATED` at compare time when both sides omit them, and a failure when only one side has them.

## Attributes

Each attribute has `name`, `domain` (`point`, `vertex`, `edge`, `face`, `corner`, `instance`, `detail`), `type` (`float`, `int`, `vector3`), `role` (`scalar`, `position`, `direction`, `color`, `uv`, `unknown`), and either `inline` or `npz`/`key`.

Houdini primitive attributes are stored as domain `face`. A point attribute and a face attribute with the same name are different keys. Values are not interpolated onto the other domain.

## Hashes

`metadata_sha256` is the sha256 of canonical JSON (`sort_keys`, compact separators) with the `hashes` object removed. Each NPZ file's bytes are hashed into `hashes.arrays`. Edit the JSON and validation fails until the file is rewritten by `save_snapshot`.

## Versions

`migrations.migrate` only rewrites a document when a function is registered for its current `schema_version`. Production ships no migration into 1.0.0 because 1.0.0 is the first schema. A file that says `2.0.0`, or that omits `schema_version`, is an error that names 1.0.0. The registry is tested with a temporary 0.9.0 → 1.0.0 rename so a future field rename has a place to live.

## Config

`parityforge.toml`:

```toml
schema_version = "1.0.0"
intent = "identity"          # or distribution

[gates]
ids = ["centroid", "bounds"] # optional; replaces the default gate list

[tolerances.centroid]
absolute = 0.001
relative = 0.0
unit = "meter"
minimum_samples = 1
```

Omitted tolerances keep the defaults in `parityforge.config`.

## Suite

`fixtures/suite.yaml` lists cases. `expect` is an assertion checked after the verdict. The comparison engine does not read `expect`, so a fixture cannot pass by declaring that it should.

## Report

`report.json` uses `schema_version` `1.0.0` as well. Fields that matter for automation: `overall`, `intent`, `equality_claim`, `labels`, `summary`, `gates`, `metrics[]` (`id`, `status`, `gated`, `value`, `tolerance`, `rationale`).
