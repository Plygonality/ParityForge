# Unreal adapter contract (deferred to v0.2)

v0.1 does not capture Unreal. `parityforge.hosts.unreal.capture_unreal` raises `HostError`. Doctor reports `deferred` and lane `NOT_RUN`. No screenshot, point count, or parity percentage from Unreal is published.

## What a v0.2 adapter would have to do

Run inside the Unreal Editor process. The `unreal` module is not a pip package and is not available to `hython` or CPython. Headless `UnrealEditor-Cmd` Python is version-dependent, often requires a project, and does not expose a stable "cook this PCG graph and return points" call. If that call is missing, the adapter must stop and record `UNSUPPORTED`. It must not synthesize points.

## Coordinate contract, already tested

The basis is the one NodeBridge documents, and ParityForge tests it without an Editor:

* Left-handed, Z-up, forward +Y relative to Blender's -Y.
* `matrix_to_canonical` is `diag(1, -1, 1)`.
* `meters_per_unit` is `0.01` (one Unreal unit is one centimeter).
* Determinant is -1. A handedness flip reverses winding; area uses the absolute cross product, and topology comparisons must say so.

## Known Editor-Python limits to preserve

* PCG graphs are point processors. Mesh topology from a Geometry Nodes extrude is not a PCG result. Comparing those as vertex-identical meshes would be the wrong metric; the NodeBridge support matrix marks mesh modelling on PCG as UNSUPPORTED.
* PCG Python can fail to create graph parameters. Script-level constants are not the same thing as a cooked attribute.
* Static Mesh Spawner output depends on the mesh asset assigned in the project. A missing asset is a capture failure, not an empty pass.
* Editor Python must not be required for `parityforge compare`. The snapshot format is the boundary.

## Suggested snapshot contents

One object per PCG output pin that actually cooked: instance or point positions in Unreal units, the component transform, the graph asset path, the seed, and the parameter values used for that cook. Attribute domain stays explicit. Image comparison stays out of the quality gate until camera and renderer differences are modeled.
