# Limitations

These are the limits of v0.1, including what was not run.

## Not a compiler

ParityForge does not translate node graphs, emit VEX, or build Houdini networks. NodeBridge's EQUIVALENT class is quoted from its report. It is not a measured distance.

## Authored fixtures are not live cooks

The four demonstration cases are written by `parityforge.authoring`. Their `source_version` is `fixture`. They prove the offline metric rules, including an intentional 0.4 m failure. They do not prove that a particular `.blend` and `.hip` agree. The NodeBridge scatter link says this in `link.json`: the evaluated arrays are independent uniform samples chosen to illustrate an EQUIVALENT scatter, not the output of `examples/scatter/generated_houdini.py`.

## Host lanes

* Blender capture is implemented against `bpy`'s evaluated depsgraph. v0.1 ran it in Blender 4.5.14 LTS: a factory-startup plane captured through `scripts/blender_demo.py` matched the authored Houdini centimeter fixture on point count, face count, centroid, surface area, Hausdorff distance, and bounds. Vertex identity stayed `NOT_EVALUATED`. The same pair under the default identity gates is an overall FAIL, because the live snapshot has empty `parameters` and Blender's built-in attributes (`position`, selection, `sharp_face`, corners), while the fixture declares `size_x`, `size_y`, and `scale_x` and no attributes. Centroids still differ by 0.0 m. `UVMap` (`FLOAT2`) and `.edge_verts` (`INT32_2D`) are warnings, not silent passes. That session is not a substitute for a Houdini cook of the same scene.
* Houdini capture is implemented against `hou` and is covered by a structural fake in unit tests. That fake is not a Houdini session. If `hython` cannot import `hou`, doctor reports the lane `NOT_RUN`. CI on GitHub-hosted runners asserts that absence. No Houdini license was available while building v0.1.
* Unreal is not implemented. No Editor session was run. See [unreal_v0.2.md](unreal_v0.2.md).

## Comparison limits

* No ICP, no centroid subtraction, no automatic scale fit. A real offset stays a failure under identity tolerances.
* Vertex identity requires `correspondence = "index"` on both sides and equal counts. Otherwise the metric is `NOT_EVALUATED`.
* Distributional passes do not claim shared point ids. The Hausdorff distance and the 99th-percentile nearest-neighbour distance are still reported.
* Surface area is the absolute area of a fan triangulation. Non-manifold or unfaced point clouds do not receive a passing area.
* Edge-domain attributes are listed and marked `UNSUPPORTED`. They are not dropped and they are not scored.
* Vector attributes with `role = "unknown"` are inconclusive. Direction attributes under non-uniform scale are inconclusive, because v0.1 does not apply an inverse-transpose.
* Image comparison is `UNSUPPORTED` even when a thumbnail path is present.
* Object pairing is by name, except when each snapshot has exactly one object. A rename in that case is a warning, not a silent extra alignment.
* Houdini centimeters are only honored when the snapshot says `meters_per_unit = 0.01`. The capture script will not guess that a hip is in centimeters.
* The Houdini basis is the NodeBridge geometry basis (Blender -Y → Houdini +Z). It is not a claim about Houdini's camera look axis.
* Seeds are compared as declared integers. ParityForge does not reproduce Blender's or Houdini's random streams.

## Numeric reporting

Report floats are rounded to 9 significant digits, and magnitudes below `1e-12` print as 0. The exact-pass flag uses `1e-9` on the raw delta, which is far below the millimeter identity tolerances.

## What a passing suite does not mean

`parityforge suite fixtures/suite.yaml` checks that the verifier still produces the expected verdicts for the authored fixtures. A green suite is not a certificate that every Geometry Nodes tree matches Houdini.
