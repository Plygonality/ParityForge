# Troubleshooting

## `capture_blender.py must run inside Blender`

The script was started with system Python. `bpy` is not installed there on purpose. From the repository root:

```bash
blender --background scene.blend --python scripts/capture_blender.py -- --out snapshots/scene.snapshot.json
```

The `--` is required. Arguments before it belong to Blender and never reach the script. `--help` works in system Python and prints the same `--out` flag.

Blender older than 3.6 exits with a version error. The evaluated depsgraph and `mesh.attributes` are the reason for that floor.

## `This host interpreter cannot import: pydantic`

`blender --python` uses the Python inside the Blender install. Packages installed for the `python` on `PATH` are invisible there. Official builds include numpy. They do not include pydantic, and the snapshot writer uses it to reject an invalid document before writing it.

```bash
python tools/install_blender_host_deps.py --blender /path/to/blender
```

The tool finds `<blender-dir>/<version>/python/bin/python3.*` (or `Contents/Resources` inside a macOS app) and runs `ensurepip` plus `pip install 'pydantic>=2.7,<3'` with that binary. The same step is in the Blender CI job.

hython has the same split. When that hython provides pip, `hython -m pip install 'pydantic>=2.7,<3' numpy` is the equivalent. v0.1 did not execute it.

## `capture_houdini.py must run inside hython`

```bash
hython scripts/capture_houdini.py --hip scene.hip --node /obj/geo1/OUT --out snapshots/scene.snapshot.json
```

`--node` has to be a SOP with geometry. `/obj/geo1` is a container and is rejected. If `hython` exists but `import hou` fails, doctor reports `found_but_unusable` and the lane stays `NOT_RUN`. A license dialog is not treated as a successful version probe.

`--meters-per-unit 0.01` records centimeters. The default is 1. A wrong value shows up as a scale error in the centroid, which is what you want.

## Metadata hash mismatch

The JSON was edited after sealing, or it was not written by ParityForge. The error prints the declared hash and the recomputed hash. Rebuild with the capture script or `python tools/build_fixtures.py`. Validation will not skip the check.

## Unsupported schema_version

Only `1.0.0` is accepted. A newer file is not guessed into the old shape. The message names the supported version and points at this document set.

## Identity compare is INCONCLUSIVE

Vertex positions are gated for `intent = "identity"` and stay `NOT_EVALUATED` when `correspondence` is `none`. Live captures write `none` because index `i` in Blender is not known to be index `i` in Houdini. Either declare correspondence when you really have it, or compare with `intent = "distribution"`, or set an explicit gate list that uses `hausdorff` and `centroid` instead of `vertex_position`. The live Blender test does the last of those and still reports vertex identity as `NOT_EVALUATED`.

## Distribution compare passed but the points look different

That is the intended reading. Check `cross_nn_p99` and `hausdorff`. They are computed and, for the seeded scatter fixture, they fail their tight default tolerances. They are not on the distribution gate. The summary lists them under ungated failures. The equality claim is statistical similarity.

## A 0.4 m move still passed

Identity tolerances are 1 mm. The scatter config widens centroid to 0.25 m because 5,000 uniform samples on a 10 m square do not share a centroid to the millimeter. Use the identity config when the geometry is supposed to be the same shape in the same place. Do not reuse the scatter tolerances for a transformed primitive.

## Doctor says Blender is unavailable

Set `PARITYFORGE_BLENDER` to the real executable, or put `blender` on `PATH`. Doctor does not search an application bundle it has not been told about, and it does not report a version it did not run.

## Images

Thumbnail paths are links. They are not scored. A missing thumbnail is a warning, not a pass, and the image metric stays `UNSUPPORTED`.
