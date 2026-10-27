# -*- coding: utf-8 -*-
"""Real OBJ -> Blender -> cuboids regression for the flat-colour texture bug."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

import numpy as np
from PIL import Image

from bbmodel import validate_project
from voxel_surface import FACE_FRAMES


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--output", type=Path, required=True)
    cli.add_argument("--blender", required=True)
    args = cli.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    vertices, mtl = [], []
    for i, (name, (corner, right, down, normal)) in enumerate(FACE_FRAMES.items()):
        corner, right, down = (np.array(v) for v in (corner, right, down))
        vertices.extend("v %g %g %g" % tuple(p) for p in (corner, corner + right, corner + down, corner + right + down))
        vertices.extend(["vt 0 1", "vt 1 1", "vt 0 0", "vt 1 0", "usemtl " + name])
        k = i * 4 + 1
        vertices.append("f %d/%d %d/%d %d/%d %d/%d" % (k, k, k + 2, k + 2, k + 3, k + 3, k + 1, k + 1))
        image = Image.new("RGBA", (16, 16))
        for y in range(16):
            for x in range(16):
                image.putpixel((x, y), (20 + x * 14, 20 + y * 14, 30 + i * 35,
                                        0 if name == "south" and x < 4 and y < 4 else 255))
        image.save(args.output / (name + ".png"))
        mtl.extend(["newmtl " + name, "Kd 1 1 1", "map_Kd " + name + ".png"])
        if name == "south":
            image.getchannel("A").save(args.output / "south_alpha.png")
            mtl.append("map_d south_alpha.png")
    source = args.output / "six_faces.obj"
    source.write_text("mtllib six_faces.mtl\no six_faces\n" + "\n".join(vertices) + "\n", encoding="ascii")
    (args.output / "six_faces.mtl").write_text("\n".join(mtl), encoding="ascii")
    output = args.output / "surface"
    subprocess.run([sys.executable, str(Path(__file__).with_name("convert.py")), str(source), str(output),
                    "--blender", args.blender, "--voxel-resolution", "8", "--fit-size", "4",
                    "--voxel-texture-density", "2", "--texture-resolution", "16", "--geo"], check=True)
    document = json.loads(next(output.glob("*.bbmodel")).read_text(encoding="utf-8"))
    validate_project(document)
    assert len(document["elements"]) == 1, "Solid differently coloured cube must merge into one cuboid"
    assert len(document["textures"]) == 1, "All materials must share one Minecraft atlas"
    assert not document["meta"]["box_uv"]
    cube = document["elements"][0]
    atlas = Image.open(document["textures"][0]["path"]).convert("RGBA")
    details = {}
    for i, name in enumerate(FACE_FRAMES):
        face = cube["faces"][name]
        patch = np.asarray(atlas.crop(tuple(face["uv"])))
        # Asymmetric X/Y ramps detect both U/V flips and wrong face assignment.
        assert patch.shape == (16, 16, 4)
        assert patch[8, 12, 0] > patch[8, 3, 0] + 70, name + " U flipped"
        assert patch[12, 8, 1] > patch[3, 8, 1] + 70, name + " V flipped"
        assert abs(int(patch[8, 8, 2]) - (30 + i * 35)) <= 1, name + " material mismatch"
        assert len(np.unique(patch.reshape(-1, 4), axis=0)) > 64, name + " collapsed to flat colour"
        if name == "south":
            assert patch[1, 1, 3] == 0 and patch[8, 8, 3] == 255, "Source alpha lost"
        details[name] = {"colours": len(np.unique(patch.reshape(-1, 4), axis=0)), "uv": face["uv"]}
    geo = json.loads(next(output.glob("*.geo.json")).read_text(encoding="utf-8"))
    exported = geo["minecraft:geometry"][0]["bones"][0]["cubes"][0]["uv"]
    assert exported["up"]["uv_size"] == [-16, -16]
    assert exported["north"]["uv_size"] == [16, 16]
    results = {"passed": True, "faces": details, "cubes": 1, "textures": 1}
    (args.output / "test_results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
