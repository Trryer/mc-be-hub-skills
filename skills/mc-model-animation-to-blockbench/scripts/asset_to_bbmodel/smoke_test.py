# -*- coding: utf-8 -*-
"""Repeatable CLI regression with real Blender imports and optional native BB check."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys

from PIL import Image

from bbmodel import validate_project
from convert import blender_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--blender")
    parser.add_argument("--output", type=Path, required=True, help="New/empty test output directory")
    parser.add_argument("--blockbench-port", type=int)
    args = parser.parse_args()
    if args.output.exists() and any(args.output.iterdir()):
        parser.error("Choose an empty output directory")
    args.output.mkdir(parents=True, exist_ok=True)
    tool = Path(__file__).parent
    blender = blender_path(args.blender)
    fixture = tool / "examples/rigged_two_clips.glb"
    fixture.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([str(blender), "-b", "--factory-startup", "--python-exit-code", "7", "--python", str(tool / "make_test_glb.py"), "--", str(fixture)], check=True)
    before = hashlib.sha256(fixture.read_bytes()).hexdigest()
    results = []
    for mode in ("mesh", "voxel"):
        output = args.output / mode
        subprocess.run([sys.executable, str(tool / "convert.py"), str(fixture), str(output), "--blender", str(blender), "--mode", mode,
                        "--voxel-resolution", "16", "--texture-resolution", "4", "--bedrock-animation", "--geckolib-animation"]
                       + (["--geo"] if mode == "voxel" else []), check=True)
        model = next(output.glob("*.bbmodel"))
        document = json.loads(model.read_text(encoding="utf-8"))
        validate_project(document)
        report = json.loads((output / "report.json").read_text(encoding="utf-8"))
        assert report["source_counts"]["bones"] == 2
        assert report["source_counts"]["meshes"] == 2, "Importer bone-shape widgets must not become geometry"
        assert {a["name"] for a in document["animations"]} == {"idle", "attack"}
        assert any(k["interpolation"] == "step" for a in document["animations"] for b in a["animators"].values() for k in b["keyframes"]), "STEP source interpolation lost"
        assert all(g["name"].isascii() for g in document["groups"])
        assert any(Image.open(p).convert("RGBA").getextrema()[3][0] < 255 for p in (output / "textures").glob("material_*.png"))
        assert max(Image.open(output / "textures/material_000.png").size) <= 4
        if mode == "voxel":
            assert len(document["textures"]) == 1, "Voxel output should use one Minecraft atlas"
            assert len(report["voxel"]["sampled_source_materials"]) >= 2, "Material samples lost"
        else:
            assert len({f["texture"] for e in document["elements"] for f in e["faces"].values()}) >= 2, "Material assignments lost"
        if args.blockbench_port:
            subprocess.run([sys.executable, str(tool / "validate_in_blockbench.py"), str(model), "--port", str(args.blockbench_port)], check=True)
        results.append({"case": "animated_glb_" + mode, "passed": True, "elements": len(document["elements"])})
    assert hashlib.sha256(fixture.read_bytes()).hexdigest() == before

    # Convert the exact GLB payload into glTF with an external BIN. Keeps real
    # skins, embedded-image bufferViews and all clips, testing path resolution.
    data = fixture.read_bytes()
    json_length = struct.unpack_from("<I", data, 12)[0]
    document = json.loads(data[20:20 + json_length])
    bin_start = 20 + json_length
    bin_length = struct.unpack_from("<I", data, bin_start)[0]
    document["buffers"][0]["uri"] = "rigged.bin"
    (args.output / "rigged.bin").write_bytes(data[bin_start + 8:bin_start + 8 + bin_length])
    gltf = args.output / "rigged.gltf"
    gltf.write_text(json.dumps(document), encoding="utf-8")
    subprocess.run([sys.executable, str(tool / "convert.py"), str(gltf), str(args.output / "external_gltf"), "--blender", str(blender), "--mode", "mesh"], check=True)
    results.append({"case": "external_gltf", "passed": True})

    obj = args.output / "two_materials.obj"
    obj.write_text("mtllib colours.mtl\no first\nv 0 0 0\nv 1 0 0\nv 0 1 0\nv 0 0 1\nusemtl red\nf 1 2 3\no second\nusemtl blue\nf 1 4 2\n", encoding="ascii")
    (args.output / "colours.mtl").write_text("newmtl red\nKd 1 0 0\nnewmtl blue\nKd 0 0 1\nd 0.5\nmap_d alpha_mask.png\n", encoding="ascii")
    alpha_mask = Image.new("L", (2, 2))
    alpha_mask.putdata([0, 255, 255, 0])
    alpha_mask.save(args.output / "alpha_mask.png")
    subprocess.run([sys.executable, str(tool / "convert.py"), str(obj), str(args.output / "obj"), "--blender", str(blender), "--mode", "mesh"], check=True)
    obj_report = json.loads((args.output / "obj/report.json").read_text(encoding="utf-8"))
    assert any("no UV" in w for w in obj_report["warnings"])
    obj_model = json.loads(next((args.output / "obj").glob("*.bbmodel")).read_text(encoding="utf-8"))
    assert len({face["texture"] for e in obj_model["elements"] for face in e["faces"].values()}) == 2
    assert any(Image.open(p).convert("RGBA").getextrema()[3][0] == 0 for p in (args.output / "obj/textures").glob("material_*.png")), "OBJ alpha-only map lost"
    results.append({"case": "obj_mtl_missing_uv", "passed": True})

    broken = args.output / "damaged.fbx"
    broken.write_bytes(b"not a valid FBX")
    failed = subprocess.run([sys.executable, str(tool / "convert.py"), str(broken), str(args.output / "expected_import_failure"), "--blender", str(blender)])
    failed_report = json.loads((args.output / "expected_import_failure/report.json").read_text(encoding="utf-8"))
    assert failed.returncode != 0 and failed_report["status"] == "failed" and failed_report["errors"]
    results.append({"case": "damaged_input_reports_failure", "passed": True})
    summary = {"passed": True, "cases": results, "source_unchanged": True}
    (args.output / "test_results.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
