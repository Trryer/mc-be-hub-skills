# Complex animation validation

Use this workflow when a clip contains multiple revolutions, several moving bones, or combined rotation and translation. Keep asset-specific matrices, screenshots, counts and acceptance records in the project or an external record store.

## Preserve the action through baking

Evaluate the source hierarchy, including FBX pivots, pre/post rotations and bind transforms, with the importer. Convert geometry, bone pivots and motion through the same axis/unit mapping. A first animation pose may differ from the bind pose; validate the static binding separately.

Sample the evaluated source at `--fps` plus exposed source key times, as the converter already does. Choose the rate from the fastest changing part, rather than the total clip length. Increase it when representative intermediate poses fail comparison. A small difference between sampled rotation matrices cannot rule out an entire revolution between samples: inspect source curves or add samples around rapid motion before accepting the bake.

The converter keeps quaternion hemisphere continuity in its ASCII FBX bridge, uses compatible Euler branches while baking, and writes quaternion interpolation for Blockbench bone animators. Preserve intermediate rotation samples when simplifying keys. Identical first and last orientations can still represent several turns; collapsing them or interpolating only between endpoints loses the path. Equivalent Euler triples are not themselves an error; compare evaluated poses and motion direction.

## Compare the complete hierarchy

The bundled `validation_checkpoints.json` contains first/middle/last samples per clip. For complex motion, extend the source reference to cover all baked times and representative times between keys, including rotation reversals, translation extremes, short transitions and the beginning/end of a hold. Use independently evaluated source transforms rather than reconstructing the reference from the exported keyframes.

Compare in a shared space. With column-vector matrices, let `C` map source coordinates into Blockbench units, `W_source(t)` be the evaluated source bone world transform, and `W_bb(t)` the exported group world transform:

```text
D_source(t) = C * W_source(t) * inverse(W_source(bind)) * inverse(C)
D_bb(t)     = W_bb(t) * inverse(W_bb(bind))
```

Both deformations must act on the same bound points. When an importer supplies geometry-to-bone matrices or a different bind convention, derive the reference from its actual skin/bind relation. For relative-motion checks, the same reference time can replace `bind` on both sides, but that check must accompany a separate static bind-pose comparison.

Evaluate every bone in parent order. Blockbench group origins are absolute model-space pivots; local base translations subtract the parent's origin. Apply the target format's base rotations, animated offsets, scale and interpolation before multiplying through the parent chain. The bundled exporter uses Blender extrinsic XYZ matrices corresponding to Blockbench/THREE intrinsic ZYX; do not compare raw Euler numbers across these conventions.

Apply both deformations to a part's bound vertices or representative bound corners. Report maximum point error in Blockbench units, bone and time of the worst error, and the number of checked bones/times. Relate tolerance to the current model scale and voxel pitch; key count or matrix agreement at three checkpoints is insufficient. Check between-key poses as well as exact keys, because interpolation can differ while the keys agree.

## Check playback and each requested resolution

- Retain clip duration, source pauses and action order. Select `--loop` from source metadata or the user's intent; inspect auto-inference warnings. Different endpoint poses do not justify inventing a reverse pass or a transition. A repeating preview GIF does not change an exported `once` clip into a looping animation.
- Play the source action with the camera and any preview turntable fixed, then inspect it from other angles. An extra whole-model spin belongs to the preview unless requested in the asset. For requested loops, observe at least three cycles and compare the same action phases, including the boundary.
- Voxel resolution controls geometry sampling; `--fit-size` controls model size; `--fps` controls animation sampling. Changing one should not silently change the other two. Compare clip names, durations, loop modes and evaluated bone motion across every requested geometry resolution. Different UUIDs and cube counts are expected.
- Inspect textured previews at representative poses and continuously through the moving section. Check pivots, part connections and texture attachment. Open each delivered project in Blockbench and play every clip when native validation is available; verify optional Bedrock geometry/animation exports together.

Record JSON/structure checks, numerical source comparisons, offline previews, native Blockbench checks, user confirmation and Minecraft runtime checks separately. An offline TRS evaluator is useful evidence, but is not the native codec. Preserve untested items explicitly; Blockbench acceptance does not establish game performance or smooth blended skinning support.
