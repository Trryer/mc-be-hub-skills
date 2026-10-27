# Conversion workflow

## Inspect the asset

Check the source format and version, adjacent MTL/BIN/texture files, axes and units, object or bone hierarchy, model bounds, materials, UVs, and every available animation clip. OBJ usually supplies static geometry. If the source has no linked albedo image, obtain the correct PNG/JPEG and pass `--albedo`. That option applies one image to all source materials while retaining their UVs.

## Install and run

The converter requires Python 3.11+ and Blender 4.5+. Resolve the folder containing this skill’s `SKILL.md`, then set `$tool` to its `scripts/asset_to_bbmodel` directory. For example, for a local installation:

```powershell
$skillRoot = 'C:/Users/<user>/.codex/skills/mc-model-animation-to-blockbench'
$tool = Join-Path $skillRoot 'scripts/asset_to_bbmodel'
```

In a copied package, set `$skillRoot` to the folder containing the copied `SKILL.md`. Install the regular dependencies from a virtual environment:

```powershell
python -m pip install -r (Join-Path $tool 'requirements.txt')
python (Join-Path $tool 'convert.py') --help
```

Set `BLENDER_PATH` to `blender.exe` or pass `--blender`. Blender must be able to run in background mode. ASCII FBX uses ufbx 0.0.5 in an isolated Python process; binary FBX uses Blender by default. For ASCII FBX, install `requirements-fbx.txt` into Python 3.11 and pass that interpreter:

```powershell
py -3.11 -m venv .venv-fbx
./.venv-fbx/Scripts/python.exe -m pip install -r (Join-Path $tool 'requirements-fbx.txt')
python (Join-Path $tool 'convert.py') input.fbx output --blender "$env:BLENDER_PATH" --fbx-python ./.venv-fbx/Scripts/python.exe
```

The output folder must be new or empty. Keep converter code and generated projects outside the source asset folder.

```powershell
# Default voxel model: 80 cells along the longest dimension
python (Join-Path $tool 'convert.py') input.fbx output --blender "$env:BLENDER_PATH"

# Higher voxel preset, plus Bedrock geometry and animation exports
python (Join-Path $tool 'convert.py') input.fbx output112 --blender "$env:BLENDER_PATH" --voxel-resolution 112 --bedrock-animation --geo --loop hold

# Preserve triangles and original UVs for a Blockbench Generic Mesh project
python (Join-Path $tool 'convert.py') input.glb output_mesh --blender "$env:BLENDER_PATH" --mode mesh
```

The four voxel presets are **48, 80, 112 and 144** cells along the longest dimension. The default is **80** when the user gives no precision requirement. Pass any integer >=8 with `--voxel-resolution` for a custom resolution; model-specific cube, texture and occupied-cell budgets still apply. A budget failure must be reported rather than silently lowering resolution or dropping geometry. `--max-voxel-cells` defaults to 4,000,000, and can be explicitly adjusted when the required resources are available.

| Preset | Use |
| --- | --- |
| 48 | Smaller output and lower conversion cost |
| 80 | Default balance |
| 112 | More surface detail |
| 144 | Finer sampling with potentially larger output |

`--fit-size` separately controls model dimensions in Blockbench units. Mesh mode retains triangles and UVs and may create very large projects. Use `--fps` to control animation bake rate and `--loop auto|once|loop|hold` to select playback semantics. Inspect `report.json`, `blender.log`, and `fbx_bridge.log` for source counts, clips, warnings, or failed imports.

User-owned workflows, if provided, are read from external private storage. Keep their implementation, case data and evidence outside the public skill and distribution.

## Animation and fidelity limits

Bound skeleton and hierarchy animation clips become Blockbench bone groups with local position, rotation, and scale keyframes. Clip duration and source key times are retained where the importer exposes them. Cubic curves and constraints are sampled and baked; editable source curve handles are not preserved. Mixed STEP interpolation in the ASCII FBX bridge is approximated with short sample brackets. The ufbx bridge requires triangulated mesh faces; non-triangles fail clearly.

The converter does not write arbitrary vertex skin weights. Faces are rigidly assigned to the bone with the strongest accumulated influence, so blended joints can split or look stiff. Voxel cubes approximate curved surfaces and thin sheets. Generic Mesh retains triangles and UVs but may be impractical for dense assets. Morph-target animation, PBR material behavior, and custom source normals are not reconstructed losslessly. Review loop inference warnings instead of silently changing intended playback.

## Validate in Blockbench

Inspect `report.json` and open the generated `.bbmodel` in Blockbench. Select and play every clip; verify texture placement, pivots, bone movement, duration, and loop/hold behavior. If Bedrock exports were requested, verify the `.geo.json` and `.animation.json` together.

The bundled `smoke_test.py` creates its own GLB test fixture and exercises GLB, external glTF, OBJ+MTL, voxel and mesh paths, and damaged-input reporting. Run it with a new temporary output folder:

```powershell
python (Join-Path $tool 'smoke_test.py') --blender "$env:BLENDER_PATH" --output "$env:TEMP/bbmodel-converter-smoke"
```

For native codec testing, install `websocket-client`, launch Blockbench with a new user-data directory and a local debug port, then run `validate_in_blockbench.py` on the output. The validator closes documents inside its target profile; never point it at an active editing profile. Blockbench success does not prove Minecraft entity integration or target-device performance.

Validate the selected resolution against the current asset; passing one preset or a synthetic fixture does not prove another asset's appearance, animation quality or game performance.
