# Changelog

## 0.1.0

First release of the offline verifier and the Blender/Houdini capture scripts.

* Snapshot schema 1.0.0 with JSON metadata, NPZ arrays, and sha256 seals.
* Comparison intents `identity` and `distribution`, with PASS, FAIL, INCONCLUSIVE, UNSUPPORTED, and NOT_EVALUATED.
* Declared Blender, Houdini, and Unreal bases. Unit scale stays in `meters_per_unit`. No ICP.
* Four authored fixtures: transformed primitive, 0.4 m transform failure, seeded scatter, attribute-domain mismatch.
* Optional NodeBridge scatter report link at audited commit `21d5ca9cc43f09ac173a5e487003f6bc13ac33bf`. The link does not cook NodeBridge output.
* `parityforge validate`, `compare`, `suite`, and `doctor`.
* Host capture for Blender ≥ 3.6 and Houdini ≥ 19.5. Missing hosts stay NOT_RUN.
* Capture records canonical `extent_*_m` and `scale_*` parameters. Blender bookkeeping attributes (`.*`, `position`, `sharp_face`) are warnings, not schema entries. User attributes remain in the schema.
* `tools/install_blender_host_deps.py` installs pydantic into Blender's own Python. A system pip install does not reach `blender --python`.
* Unreal capture is an explicit error. The v0.2 contract is documented and not executed.
