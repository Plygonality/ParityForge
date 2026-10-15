# Gap audit (2026-10-15)

ParityForge was an empty repository: one README sentence and the initial commit. This audit records the sibling projects that were inspected before any comparison code was written. Nothing in those repositories was modified.

## Repositories

| Repository | State on 2026-10-15 | What ParityForge does with it |
| --- | --- | --- |
| [NodeBridge](https://github.com/Plygonality/NodeBridge) `21d5ca9cc43f09ac173a5e487003f6bc13ac33bf` | Blender node-tree compiler. Semantic IR, fidelity classes EXACT / EQUIVALENT / APPROXIMATE / UNSUPPORTED, text translation reports, generated Houdini and Unreal Python. Coordinate and unit conventions are documented and tested. Live Houdini and Unreal execution is explicitly not verified by NodeBridge itself. | Read the README, architecture, support matrix, scatter example, expected Houdini report, and `common/coordinates.py`, `common/units.py`, `common/random.py`. ParityForge does not import NodeBridge and does not compile graphs. An optional fixture parses the published scatter report and links it to evaluated snapshots. |
| [Plygon-mcp](https://github.com/Plygonality/Plygon-mcp) | Local MCP bridges for Blender (`127.0.0.1:9876`) and Houdini (`127.0.0.1:9877`). GUI integration. A cloud agent cannot reach a desktop DCC on that loopback. | Not a dependency. Core verification never starts an MCP server, calls an LLM, or requires a network. |
| `Plygonality/Blend-ci` | GitHub returned `Could not resolve to a Repository`. The org listing on this date is NodeBridge, ParityForge, Plygonality, and Plygon-mcp. | Nothing to reuse. Headless Blender invocation follows Blender's own `--python` / `--` convention, which NodeBridge also documents for its example builder. |
| gn-as-code, HDA-as-code, Pcg-as-code | Not present in the org and not publicly installable from here. | Optional fixture producers only. No import, no assumed API. |

## What already exists, and the gap

NodeBridge answers "what does this node tree mean, and what native network implements that meaning?" Its scatter report is explicit that Distribute Points on Faces becomes a Scatter SOP with the same density and different random positions, class EQUIVALENT. It does not measure the cooked point clouds.

Plygon-mcp answers "can a local agent see and edit the open scene?" It is a GUI bridge.

Nobody in this org, as of the audit, answers "after both DCCs evaluate, where do the geometry, attributes, transforms, and instance distributions agree?" Matching a node count, a translation-report class, or a screenshot does not answer that.

## What ParityForge owns

1. Capture adapters that record evaluated geometry from inside Blender or Houdini.
2. A versioned snapshot (JSON metadata, NPZ arrays) with basis, units, seeds, and hashes.
3. An offline comparison engine with separate structural, numerical, distributional, and attribute metrics.
4. JSON and HTML reports whose statuses are PASS, FAIL, INCONCLUSIVE, UNSUPPORTED, or NOT_EVALUATED.

## What ParityForge deliberately does not own

* Node compilation, Semantic IR, or fidelity assignment. Those stay in NodeBridge. A fidelity class is context on a report, not a measurement.
* A second USD importer or a Houdini/Unreal bridge.
* Silent rigid alignment. Translation and rotation differences are reported.
* Unreal PCG capture in v0.1. The contract is in [unreal_v0.2.md](unreal_v0.2.md). No Unreal numbers are invented.

## Conventions reused from NodeBridge

These are implemented independently and checked with hand-computed vectors, not by importing NodeBridge.

| Source frame | Canonical (Blender-like) relationship |
| --- | --- |
| Blender, right-handed, Z-up, forward -Y | Identity |
| Houdini, right-handed, Y-up | `(x, y, z)` Blender → `(x, z, -y)` Houdini. Forward -Y lands on +Z. Determinant +1. |
| Unreal, left-handed, Z-up | `(x, y, z)` → `(x, -y, z)`. Determinant -1. Centimeters are `meters_per_unit = 0.01`, not part of the basis. |

NodeBridge's deterministic `random(seed, id)` is a property of generated code. It does not reproduce Blender's generator. ParityForge therefore treats equal declared seeds as a structural fact and measures sample positions separately. Equal seeds plus equal counts are not vertex identity.
