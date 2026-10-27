# Blockbench converter

Standalone local CLI included with `mc-model-animation-to-blockbench`.

Requires Python 3.11+ and Blender 4.5+. Install `requirements.txt` for the main CLI. ASCII FBX additionally uses ufbx 0.0.5; install `requirements-fbx.txt` into a Python 3.11 environment and pass its executable with `--fbx-python`. Binary FBX defaults to Blender.

```powershell
$tool = '<skill-root>/scripts/asset_to_bbmodel'
python -m pip install -r (Join-Path $tool 'requirements.txt')
$env:BLENDER_PATH = 'C:/path/to/blender.exe'
python (Join-Path $tool 'convert.py') --help
python (Join-Path $tool 'convert.py') input.fbx output --bedrock-animation --geo
```

Voxel presets are 48, 80, 112 and 144 cells along the longest edge; 80 is the default. Pass `--voxel-resolution <integer >=8>` for a custom value. Occupied-cell, cube and texture budgets fail explicitly if exceeded. Use `--mode mesh` to retain triangles and UVs. Read the parent skill's `references/conversion.md` for the workflow, limits, and validation steps.
