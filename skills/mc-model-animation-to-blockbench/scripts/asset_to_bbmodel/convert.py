# -*- coding: utf-8 -*-
"""Local-only Blender -> Blockbench converter. Python 3.11+; no server."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

from bbmodel import build_project, write_exports, validate_project


def blender_path(explicit=None):
    candidate = explicit or os.environ.get("BLENDER_PATH") or shutil.which("blender")
    if candidate:
        path = Path(candidate).expanduser()
        if path.is_file():
            return path.resolve()
    roots = [Path(os.environ.get("PROGRAMFILES", "C:/Program Files")) / "Blender Foundation",
             Path("D:/Program Files/Blender Foundation")]
    for root in roots:
        matches = sorted(root.glob("Blender */blender.exe"), reverse=True)
        if matches:
            return matches[0]
    raise ValueError("Blender not found. Pass --blender PATH or set BLENDER_PATH.")


def parser():
    cli = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    cli.add_argument("input", type=Path, help=".fbx / .glb / .gltf / .obj (with adjacent MTL/textures)")
    cli.add_argument("output", type=Path, help="New/empty output directory")
    cli.add_argument("--blender", help="Blender 4.5+ executable, or BLENDER_PATH")
    cli.add_argument("--mode", choices=["voxel", "mesh"], default="voxel")
    cli.add_argument("--texture-resolution", type=int, default=256, help="Max albedo edge; 0 keeps source size")
    units = cli.add_mutually_exclusive_group()
    units.add_argument("--fit-size", type=float, default=32, help="Fit longest edge into this many BB units")
    units.add_argument("--scale", type=float, help="Explicit BB units per Blender metre; 16 = 1 MC block/metre")
    cli.add_argument("--no-center", action="store_true", help="Keep original origin instead of centring XZ/bottom Y")
    cli.add_argument("--voxel-resolution", type=int, default=80, help="Grid cells along longest edge (integer >=8); presets 48/80/112/144, or a custom value")
    cli.add_argument("--max-voxel-cells", type=int, default=4000000, help="Occupied-cell budget; fail clearly instead of truncating geometry")
    cli.add_argument("--voxel-texture", choices=["surface", "flat"], default="surface", help="Surface: per-face source albedo baking; flat: legacy solid-colour Box UV")
    cli.add_argument("--voxel-texture-density", type=int, default=2, help="Baked texture pixels per voxel edge (1..8), independent of geometry size")
    cli.add_argument("--voxel-atlas-size", type=int, choices=[256, 512, 1024, 2048, 4096], default=2048, help="Maximum single surface atlas edge; never silently paginated")
    cli.add_argument("--max-cubes", type=int, default=60000, help="Fail rather than silently truncate voxel output")
    cli.add_argument("--mesh-chunk-faces", type=int, default=20000, help="Split large native meshes without dropping triangles")
    cli.add_argument("--color-bits", type=int, default=5, help="RGB bits/channel for greedy voxel merging (1..8)")
    cli.add_argument("--fps", type=float, default=30, help="Animation bake rate; original key times are also included")
    cli.add_argument("--loop", choices=["auto", "once", "loop", "hold"], default="auto")
    cli.add_argument("--obj-up", choices=["Y", "Z"], default="Y")
    cli.add_argument("--obj-forward", choices=["X", "Y", "Z", "NEGATIVE_X", "NEGATIVE_Y", "NEGATIVE_Z"], default="NEGATIVE_Z")
    cli.add_argument("--bedrock-animation", action="store_true")
    cli.add_argument("--geckolib-animation", action="store_true")
    cli.add_argument("--geo", action="store_true", help="Voxel mode: also export Bedrock geometry")
    cli.add_argument("--keep-intermediate", action="store_true")
    cli.add_argument("--timeout", type=int, default=1800, help="Blender import/bake timeout in seconds")
    cli.add_argument("--fbx-reader", choices=["auto", "blender", "ufbx"], default="auto", help="Auto: ASCII FBX uses isolated ufbx; binary FBX uses Blender")
    cli.add_argument("--fbx-python", type=Path, help="Python with numpy/ufbx; default Blender bundled Python if available, otherwise current Python")
    cli.add_argument("--albedo", type=Path, help="Explicit PNG/JPEG albedo override for all source materials, retaining its alpha")
    return cli


def main(argv=None):
    args = parser().parse_args(argv)
    start = time.monotonic()
    report = {"tool": "asset_to_bbmodel", "version": "1.0.0", "status": "starting", "warnings": [], "errors": [],
              "input": str(args.input.resolve()), "mode": args.mode,
              "limitations": ["Rigid bone groups replace smooth skin weights; blended joints may separate.",
                              "Voxel cubes approximate curves and sample albedo per voxel; not lossless.",
                              "Constraints/quaternions/cubic animation are baked; Euler singularities cannot be eliminated universally.",
                              "Only base colour/alpha are reconstructed. PBR lighting, morph targets and material animation are not exported."]}
    report["version"] = "1.1.0"
    report["limitations"][1] = "Voxel cubes approximate curves; surface albedo is reprojected onto cuboid faces, not lossless geometry."
    if not 1 <= args.voxel_texture_density <= 8:
        print("ERROR: voxel-texture-density must be 1..8", file=sys.stderr)
        return 2
    try:
        if not args.input.is_file() or args.input.suffix.lower() not in {".glb", ".gltf", ".fbx", ".obj"}:
            raise ValueError("Input must be an existing .glb/.gltf/.fbx/.obj file.")
        if args.voxel_resolution < 8 or not 1 <= args.color_bits <= 8:
            raise ValueError("voxel-resolution must be an integer >=8; color-bits must be 1..8")
        if args.max_voxel_cells <= 0:
            raise ValueError("max-voxel-cells must be positive")
        if args.texture_resolution < 0 or args.fps <= 0 or args.fps > 240 or args.max_cubes <= 0 or args.timeout <= 0:
            raise ValueError("Invalid texture resolution/fps/cube budget/timeout")
        if args.mesh_chunk_faces <= 0:
            raise ValueError("mesh-chunk-faces must be positive")
        if (args.scale is not None and args.scale <= 0) or args.fit_size <= 0:
            raise ValueError("Scale and fit size must be positive")
        if args.geo and args.mode != "voxel":
            raise ValueError("--geo requires --mode voxel; Bedrock geometry cannot contain Generic Mesh triangles.")
        if args.output.exists() and any(args.output.iterdir()):
            raise ValueError("Output directory is not empty. Choose a new directory to avoid overwriting work.")
        blender = blender_path(args.blender)
        if args.albedo and not args.albedo.is_file():
            raise ValueError("Albedo override does not exist: " + str(args.albedo))
        if args.fbx_python and not args.fbx_python.is_file():
            raise ValueError("FBX Python does not exist: " + str(args.fbx_python))
    except (ValueError, OSError) as error:
        print("ERROR:", error, file=sys.stderr)
        return 2
    args.output.mkdir(parents=True, exist_ok=True)
    report["source_sha256"] = hashlib.file_digest(args.input.open("rb"), "sha256").hexdigest()
    report["settings"] = {k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()}
    report["blender"] = str(blender)
    try:
        with tempfile.TemporaryDirectory(prefix="asset-to-bbmodel-") as scratch:
            work = Path(scratch)
            config = dict(report["settings"], input=str(args.input.resolve()), work=str(work))
            config["albedo"] = str(args.albedo.resolve()) if args.albedo else None
            with args.input.open("rb") as source_stream:
                header = source_stream.read(32)
            use_ufbx = args.input.suffix.lower() == ".fbx" and (args.fbx_reader == "ufbx" or
                (args.fbx_reader == "auto" and not header.startswith(b"Kaydara FBX Binary")))
            (work / "config.json").write_text(json.dumps(config), encoding="utf-8")
            if use_ufbx:
                bundled = sorted(blender.parent.glob("*/python/bin/python*"))
                bundled = [p for p in bundled if p.is_file() and (p.name == "python.exe" or "." in p.name and p.suffix != ".dll")]
                fbx_python = args.fbx_python or (bundled[-1] if bundled else Path(sys.executable))
                bridge_command = [str(fbx_python), str(Path(__file__).with_name("fbx_bridge.py")), str(work / "config.json")]
                print("Reading FBX locally with isolated ufbx...", flush=True)
                with (args.output / "fbx_bridge.log").open("w", encoding="utf-8") as log:
                    parsed = subprocess.run(bridge_command, stdout=log, stderr=subprocess.STDOUT, timeout=args.timeout)
                if parsed.returncode != 0 or not (work / "fbx_bridge.json").is_file():
                    raise RuntimeError("ufbx bridge failed (exit %s); inspect fbx_bridge.log. Install numpy and ufbx==0.0.5 in %s" % (parsed.returncode, fbx_python))
                report["fbx_bridge"] = json.loads((work / "fbx_bridge.json").read_text(encoding="utf-8"))
                report["warnings"].extend(report["fbx_bridge"]["warnings"])
                shutil.copyfile(work / "fbx_bridge.json", args.output / "fbx_bridge.json")
                config["fbx_bridge_input"] = str(work / "fbx_rigid.glb")
                (work / "config.json").write_text(json.dumps(config), encoding="utf-8")
            command = [str(blender), "--background", "--factory-startup", "--disable-autoexec", "--python-exit-code", "7",
                       "--python", str(Path(__file__).with_name("blender_extract.py")), "--", str(work / "config.json")]
            print("Importing and baking locally with Blender...", flush=True)
            with (args.output / "blender.log").open("w", encoding="utf-8") as log:
                process = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, timeout=args.timeout)
            if (work / "diagnostics.json").exists():
                diagnostics = json.loads((work / "diagnostics.json").read_text(encoding="utf-8"))
                report["warnings"].extend(diagnostics.get("warnings", []))
            if process.returncode != 0 or not (work / "scene.json").is_file():
                raise RuntimeError("Blender import/bake failed (exit %s); inspect blender.log" % process.returncode)
            scene = json.loads((work / "scene.json").read_text(encoding="utf-8"))
            accumulated_warnings = list(report["warnings"])
            report.update(scene["report"])
            report["warnings"] = list(dict.fromkeys(accumulated_warnings + report["warnings"]))
            report["version"] = "1.2.0"
            if use_ufbx:
                report["source_counts"]["bones"] = report["fbx_bridge"]["source_bones"]
                report["source_counts"]["meshes"] = report["fbx_bridge"]["source_meshes"]
                report["skin"] = {k: report["fbx_bridge"][k] for k in ("weighted_vertices", "blended_vertices")}
            if args.albedo:
                report["albedo_override"] = {"path": str(args.albedo.resolve()),
                    "sha256": hashlib.file_digest(args.albedo.open("rb"), "sha256").hexdigest()}
            if args.mode == "mesh" and report["source_counts"]["triangles"] > 200000:
                report["warnings"].append("Very dense Generic Mesh: Blockbench may exhaust memory. Original triangles are retained; use voxel output when a native cuboid model is required.")
            project = build_project(scene, args, work, report)
            validate_project(project)
            model_path = args.output / (args.input.stem + "." + args.mode + ".bbmodel")
            model_path.write_text(json.dumps(project, ensure_ascii=False, separators=(",", ":"), allow_nan=False), encoding="utf-8")
            report["outputs"] = [model_path.name] + write_exports(project, args)
            report["output_counts"] = {"groups": len(project["groups"]), "elements": len(project["elements"]),
                                       "textures": len(project["textures"]), "animations": len(project["animations"])}
            report["status"] = "success_with_warnings" if report["warnings"] else "success"
            if args.keep_intermediate:
                shutil.copytree(work, args.output / "intermediate")
            print("Saved:", model_path.resolve(), flush=True)
    except (OSError, ValueError, RuntimeError, KeyError, subprocess.SubprocessError) as error:
        report["status"] = "failed"
        report["errors"].append(str(error))
        print("ERROR:", error, file=sys.stderr)
    finally:
        report["elapsed_seconds"] = round(time.monotonic() - start, 3)
        (args.output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    for warning in report["warnings"]:
        print("WARNING:", warning)
    return 1 if report["status"] == "failed" else 0


if __name__ == "__main__":
    sys.exit(main())
