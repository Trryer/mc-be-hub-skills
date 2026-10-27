---
name: mc-model-animation-to-blockbench
description: Convert static or skeletal animated GLB/glTF 2.0, FBX, and OBJ assets into editable Blockbench .bbmodel cuboid or Generic Mesh projects, including texture and bone animation baking. Use for general model or animation conversion to Blockbench, not Minecraft shader reconstruction.
---

# Model and animation to Blockbench

Use the bundled local converter in `scripts/asset_to_bbmodel/` to create native Blockbench `.bbmodel` projects from GLB/glTF 2.0, FBX, or OBJ+MTL. It supports cuboid voxel reconstruction and Generic Mesh output, texture and alpha extraction, bone groups, and baked animation clips. Optional exports include Bedrock `geo.json` and `animation.json`.

Read [the conversion workflow](references/conversion.md) for input checks, dependencies, useful presets, animation limitations, and Blockbench validation. The complete converter source, requirements, repeatable regression test, and optional desktop codec validator ship in this skill.

Voxel presets are **48 / 80 / 112 / 144**; an unspecified resolution defaults to **80**. Explicit user-defined resolutions take priority, subject to reported resource budgets. User-owned workflows and evidence stay in external private storage and are not part of the public package.
