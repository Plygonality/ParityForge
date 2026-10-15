# Architecture

ParityForge checks evaluated results. It does not compile node trees.

```
Blender bpy                         Houdini hou
evaluated depsgraph                 evaluated SOP geometry
        │                                   │
        ▼                                   ▼
 scripts/capture_blender.py        scripts/capture_houdini.py
        │                                   │
        └──────────── snapshot ─────────────┘
                     schema 1.0.0
                     JSON metadata + NPZ arrays
                              │
                              ▼
                    parityforge compare
                    declared units and basis only
                    no ICP, no recentering
                              │
                              ▼
                    report.json + report.html
                    PASS / FAIL / INCONCLUSIVE
                    UNSUPPORTED / NOT_EVALUATED
```

The offline path imports numpy, scipy, pydantic, and PyYAML. It does not import `bpy` or `hou`.

## Package

```
src/parityforge/
  cli.py                validate, compare, suite, doctor
  models.py             snapshot and config schemas
  migrations.py         versioned upgrades; unknown versions are rejected
  snapshot_io.py        JSON + NPZ, sha256 seals
  coordinates.py        named bases and unit scale
  config.py             tolerances and gates
  metrics.py            area, nearest neighbour, histograms, Wasserstein
  compare.py            pairing, canonicalization, verdicts
  report.py             JSON and self-contained HTML
  suite.py              YAML suite
  doctor.py             optional DCC probes
  nodebridge_link.py    read a NodeBridge text report
  authoring.py          deterministic fixtures
  hosts/                capture scripts, Blender's Python lookup, import guards
```

## Snapshot

`schema_version` is `1.0.0`. A snapshot records source application and version, scene and asset names, frame, declared seed, parameters, units (`meters_per_unit`), and a basis matrix that maps that application's vectors into the canonical right-handed Z-up meter frame.

Geometry points are either local (the object matrix is applied) or world (the matrix is not applied a second time). Arrays larger than the inline limit belong in a sibling `.npz`. The writer seals metadata and NPZ bytes with sha256. `validate` and `compare` recompute those hashes and refuse a mismatch.

Named bases `blender`, `houdini`, and `unreal` must match the built-in matrices. A custom name may carry its own orthogonal matrix. A basis that sneaks scale in (determinant other than ±1) is rejected; scale belongs in `meters_per_unit` or in the object matrix.

## Canonicalization

For local points `p` and row-major affine matrix `M = [A|t]`:

1. World in source units: `A p + t`.
2. Meters: multiply by `meters_per_unit`.
3. Canonical axes: multiply by `matrix_to_canonical`.

The object matrix itself is converted with `A_c = R A Rᵀ` and `t_c = meters_per_unit · R t`. Relative scale stays in `A`. Nothing estimates `R` or `t` from the point cloud.

## Metrics

| Kind | Examples | Pass means |
| --- | --- | --- |
| Structural | object, point, face, and instance counts; ids; parameter names; seeds; attribute name/domain/type; face index lists when correspondence is `index` | Exact equality. A matching count is not a geometry pass. |
| Numerical | centroid, bounds, extents, surface area, per-index vertex position, Hausdorff, 99th-percentile symmetric nearest neighbour | Absolute and relative tolerance in a declared unit. |
| Distributional | spatial-histogram total variation; 1-Wasserstein distance between within-cloud nearest-neighbour lengths | Statistical similarity of the pattern. Not instance equality. |
| Attribute | scalar and vector values on point, vertex, face, corner, instance, detail | Same domain and type, explicit index correspondence, no resampling. |
| Transform | declared translation, rotation angle, per-axis scale | The matrices agree after the basis change. |
| Image | linked thumbnails | Always UNSUPPORTED in v0.1. Never a pass. |

A metric that cannot run is `NOT_EVALUATED`. A metric outside v0.1 (edge-domain values, images) is `UNSUPPORTED`. A metric below `minimum_samples` is `INCONCLUSIVE`.

## Verdicts

Each case has an intent:

* `identity` gates counts, seeds, parameters, attribute schema and values, topology, centroid, bounds, extents, area, per-index positions, and the declared transform. Vertex positions stay `NOT_EVALUATED` unless both sides declare `correspondence = "index"`, and that unevaluated gate makes the case `INCONCLUSIVE`.
* `distribution` gates counts, seeds, parameters, attribute schema, centroid, bounds, density total variation, and nearest-neighbour Wasserstein. A pass is labeled `equivalent_in_distribution` and the equality claim is `statistical_similarity`. Per-index positions are not gated. A large Hausdorff distance stays visible as an ungated failure so a distributional pass cannot be read as "the same points".

Overall status, considering gated metrics that apply:

1. Any `FAIL` → `FAIL`
2. Any `INCONCLUSIVE`, `NOT_EVALUATED`, or `UNSUPPORTED` → `INCONCLUSIVE`
3. Otherwise `PASS`

There is no single accuracy percentage.

Tolerance form: `limit = absolute + relative * scale`. `scale` is the larger magnitude of the two measured values (or 1 for unitless histogram distances).

## Reports

`parityforge compare A B --config file.toml --out directory` writes `report.json` and `report.html`. The HTML file embeds its CSS and does not fetch anything. The summary is built from the metric values: counts, centroid magnitude, 99th-percentile nearest-neighbour distance, equality claim, overall status, and any ungated failures.

## Host capture

Host scripts run inside the DCC process. They are version-gated (Blender ≥ 3.6, Houdini ≥ 19.5) and exit with the documented command if `bpy` or `hou` cannot be imported. Blender reads `sys.argv` after `--`. hython reads normal arguments; `--` is accepted too.

Blender export uses the evaluated depsgraph, `to_mesh()` in object-local space, and `matrix_world`. Instances come from `depsgraph.object_instances` when `is_instance` is set. Houdini export reads `node.geometry()` for a SOP path, plus the parent geo node's `worldTransform`. Houdini units are whatever `--meters-per-unit` says (default 1). They are not inferred.

`parityforge doctor` probes `PATH`, `PARITYFORGE_BLENDER`, `PARITYFORGE_HYTHON`, and `HFS`. A missing executable stays unavailable. A binary that fails its version probe is `found_but_unusable`. Unreal is `deferred` and is not probed.

## NodeBridge link

`fixtures/nodebridge_scatter/` stores the scatter Houdini translation report from the audited NodeBridge commit and a `link.json`. The suite attaches the parsed fidelity class to the scatter report. The class EQUIVALENT is the compiler's claim. The ParityForge measurement is the distributional comparison of the linked snapshots. Those snapshots are authored fixtures, not a live cook of `generated_houdini.py`.
