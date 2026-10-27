# -*- coding: utf-8 -*-
"""Native bbmodel writer, checked against Blockbench's project codec.

Generic mesh preserves triangles/face-corner UVs, not smooth skin weights.
Voxel mode is a surface/solid approximation with sampled albedo, never a
lossless substitute for high-poly curved geometry.
"""
import base64
from collections import defaultdict
import io
import json
import math
from pathlib import Path
import uuid

import numpy as np
from PIL import Image, ImageDraw

from voxel_surface import FACE_FRAMES, pack_rectangles


def uid():
    return str(uuid.uuid4())


def srgb(value):
    return 12.92 * value if value <= 0.0031308 else 1.055 * value ** (1 / 2.4) - 0.055


def prepare_materials(materials, work, output, resolution):
    textures, images = [], []
    for index, material in enumerate(materials):
        factor = np.array(material["color"], dtype=float)
        if material["image"]:
            image = Image.open(work / material["image"]).convert("RGBA")
            if resolution:
                image.thumbnail((resolution, resolution), Image.Resampling.NEAREST)
            values = np.asarray(image).astype(float) / 255
            # Base colour factors are linear, PNG is sRGB. Multiply in linear.
            rgb = values[:, :, :3]
            linear = np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)
            linear *= factor[:3]
            values[:, :, :3] = np.where(linear <= 0.0031308, linear * 12.92, 1.055 * linear ** (1 / 2.4) - 0.055)
            if material["alpha_channel"] == "constant":
                values[:, :, 3] = 1
            if material.get("alpha_image"):
                with Image.open(work / material["alpha_image"]) as alpha_src:
                    alpha = alpha_src.convert("RGBA").resize(image.size, Image.Resampling.NEAREST)
                values[:, :, 3] = np.asarray(alpha.getchannel(material["alpha_channel"])).astype(float) / 255
            values[:, :, 3] *= factor[3]
            image = Image.fromarray(np.clip(values * 255 + 0.5, 0, 255).astype("uint8"))
        else:
            colour = tuple(round(max(0, min(1, srgb(float(x)))) * 255) for x in factor[:3]) + (round(factor[3] * 255),)
            if material.get("alpha_image"):
                # OBJ map_d can supply transparency without any albedo map.
                with Image.open(work / material["alpha_image"]) as alpha_src:
                    alpha = alpha_src.convert("RGBA")
                if resolution:
                    alpha.thumbnail((resolution, resolution), Image.Resampling.NEAREST)
                image = Image.new("RGBA", alpha.size, colour)
                mask = np.asarray(alpha.getchannel(material["alpha_channel"])).astype(float) * factor[3]
                image.putalpha(Image.fromarray(np.clip(mask + 0.5, 0, 255).astype("uint8")))
            else:
                image = Image.new("RGBA", (16, 16), colour)
        images.append(image)
        textures.append(texture_record(image, "material_%03d.png" % index, output))
    return textures, images


def texture_record(image, filename, output):
    directory = output / "textures"
    directory.mkdir(exist_ok=True)
    image.save(directory / filename)
    stream = io.BytesIO()
    image.save(stream, format="PNG")
    return {"uuid": uid(), "name": filename, "id": filename.removesuffix(".png"),
            "relative_path": "textures/" + filename, "path": str((directory / filename).resolve()),
            "source": "data:image/png;base64," + base64.b64encode(stream.getvalue()).decode("ascii"),
            "internal": True, "saved": True, "mode": "bitmap", "render_mode": "default", "render_sides": "double",
            "width": image.width, "height": image.height, "uv_width": image.width, "uv_height": image.height,
            "wrap_mode": "repeat"}


def groups_and_outliner(source):
    groups = [{"name": g["name"], "uuid": uid(), "origin": g["pivot"], "rotation": g["rotation"],
               "export": True, "visibility": True, "isOpen": True, "children": []} for g in source]
    nodes = [{"uuid": g["uuid"], "children": []} for g in groups]
    roots = []
    for i, g in enumerate(source):
        (roots if g["parent"] is None else nodes[g["parent"]]["children"]).append(nodes[i])
    return groups, nodes, roots


def build_meshes(scene, groups, textures, images, report, chunk_faces):
    partitions = {}
    for mesh_index, mesh in enumerate(scene["meshes"]):
        for tri in mesh["triangles"]:
            key = (mesh_index, tri["bone"], tri["material"])
            partitions.setdefault(key, []).append(tri)
    elements, owners = [], []
    outside = 0
    chunks = [(key, triangles[i:i + chunk_faces]) for key, triangles in partitions.items() for i in range(0, len(triangles), chunk_faces)]
    for (mi, bone, material), triangles in chunks:
        source = scene["meshes"][mi]
        pivot = np.array(groups[bone]["origin"])
        world_to_local = np.array(scene["groups"][bone]["world_to_local"])
        image = images[material]
        used = sorted({v for tri in triangles for v in tri["v"]})
        vertices = {"v" + str(v): (world_to_local @ np.array(source["vertices"][v] + [1]))[:3].tolist() for v in used}
        faces = {}
        for fi, tri in enumerate(triangles):
            keys = ["v" + str(v) for v in tri["v"]]
            uv = {key: [source_uv[0] * image.width, (1 - source_uv[1]) * image.height] for key, source_uv in zip(keys, tri["uv"])}
            outside += any(x < 0 or x > 1 for source_uv in tri["uv"] for x in source_uv)
            if len(set(keys)) < 3:
                report["warnings"].append("Degenerate triangle skipped in " + source["name"])
                continue
            faces["f" + str(fi)] = {"vertices": keys, "uv": uv, "texture": material}
        elements.append({"name": "%s_%s_m%d_part%d" % (groups[bone]["name"], mi, material, len(elements)), "uuid": uid(), "type": "mesh",
                         "origin": pivot.tolist(), "rotation": [0, 0, 0], "vertices": vertices, "faces": faces,
                         "visibility": True, "export": True})
        owners.append(bone)
    if outside:
        report["warnings"].append("%d triangles use UVs outside [0,1]; UVs retained with repeat wrapping. Review source clamp/mirror/UV transforms." % outside)
    report["rigid_assignment"] = "Per-triangle sum of bone weights; seams duplicated at bone/material partitions. No weights exported."
    return elements, owners


def sample_colour(image, uv):
    u, v = uv
    x = min(image.width - 1, int((u % 1) * image.width))
    y = min(image.height - 1, int((1 - (v % 1)) * image.height))
    return image.getpixel((x, y))


def greedy_boxes(cells):
    """Merge only cells with the same rigid bone, material and quantized RGBA."""
    cells = dict(cells)
    boxes = []
    for start in sorted(cells):
        if start not in cells:
            continue
        value = cells[start]
        x, y, z = start
        nx = 1
        while cells.get((x + nx, y, z)) == value:
            nx += 1
        ny = 1
        while all(cells.get((xx, y + ny, z)) == value for xx in range(x, x + nx)):
            ny += 1
        nz = 1
        while all(cells.get((xx, yy, z + nz)) == value for xx in range(x, x + nx) for yy in range(y, y + ny)):
            nz += 1
        for xx in range(x, x + nx):
            for yy in range(y, y + ny):
                for zz in range(z, z + nz):
                    del cells[(xx, yy, zz)]
        boxes.append((start, (nx, ny, nz), value))
    return boxes


def build_cubes(scene, groups, images, args, report):
    data = scene["voxels"]
    factor = 2 ** args.color_bits - 1
    buckets = defaultdict(dict)
    for voxel in data["cells"]:
        colour = sample_colour(images[voxel["material"]], voxel["uv"])
        if colour[3] == 0:
            continue
        quantized = tuple(round(round(c / 255 * factor) / factor * 255) for c in colour[:3]) + (colour[3],)
        buckets[voxel["bone"]][tuple(voxel["cell"])] = (voxel["material"], quantized)
    boxes = [(bone, *box) for bone, cells in buckets.items() for box in greedy_boxes(cells)]
    if len(boxes) > args.max_cubes:
        raise ValueError("%d cubes exceed --max-cubes %d. Lower --voxel-resolution/--color-bits; output was not truncated." % (len(boxes), args.max_cubes))
    elements, owners, textures = [], [], []
    pending = defaultdict(list)
    for i, (bone, start, size, (material, colour)) in enumerate(boxes):
        lower = np.array(data["origin"]) + np.array(start) * data["step"]
        upper = lower + np.array(size) * data["step"]
        # The legacy flat-colour atlas reserves a ceil-sized solid patch;
        # Blockbench itself floors Box UV sizes. Fractional surface-textured
        # cubes therefore use build_surface_cubes/per-face UV instead.
        dx, dy, dz = np.ceil(np.array(size) * data["step"] - 1e-8).astype(int)
        dx, dy, dz = max(1, dx), max(1, dy), max(1, dz)
        element = {"name": groups[bone]["name"] + "_voxel_" + str(i), "uuid": uid(), "type": "cube",
                   "from": lower.tolist(), "to": upper.tolist(), "origin": groups[bone]["origin"],
                   "rotation": [0, 0, 0], "inflate": 0, "box_uv": True, "uv_offset": [0, 0],
                   "faces": {}, "visibility": True, "export": True}
        pending[material].append((element, tuple(int(s) for s in (dx, dy, dz)), colour))
        elements.append(element)
        owners.append(bone)
    # Shelf pack independent material pages; all pages use identical size because
    # Bedrock format has one project UV resolution (Generic supports per texture).
    max_patch = max((2 * (s[0] + s[2]) + 2 for items in pending.values() for _, s, _ in items), default=16)
    atlas_size = 2 ** math.ceil(math.log2(max(256, max_patch)))
    atlas_size = max(atlas_size, min(2048, 2 ** math.ceil(math.log2(max(256, math.sqrt(sum((2 * (s[0] + s[2]) + 2) * (s[1] + s[2] + 2) for items in pending.values() for _, s, _ in items)))))))
    for material, items in sorted(pending.items()):
        atlas = Image.new("RGBA", (atlas_size, atlas_size))
        draw = ImageDraw.Draw(atlas)
        page, x, y, row = 0, 1, 1, 0
        for element, (dx, dy, dz), colour in items:
            width, height = 2 * (dx + dz), dy + dz
            if height + 2 > atlas_size:
                raise ValueError("Box UV patch too large for atlas; reduce --fit-size or --scale")
            if x + width + 1 > atlas_size:
                x, y, row = 1, y + row + 2, 0
            if y + height + 1 > atlas_size:
                textures.append(texture_record(atlas, "voxel_m%d_p%d.png" % (material, page), args.output))
                page += 1
                atlas = Image.new("RGBA", (atlas_size, atlas_size))
                draw = ImageDraw.Draw(atlas)
                x, y, row = 1, 1, 0
            texture_index = len(textures)
            element["uv_offset"] = [x, y]
            # Standard Minecraft unfolded Box UV; entire patch is one sampled
            # albedo RGBA. UV orientation is therefore stable on all six sides.
            draw.rectangle((x - 1, y - 1, x + width, y + height), fill=colour)
            rects = {"east": [0, dz, dz, dz + dy], "west": [dz + dx, dz, 2 * dz + dx, dz + dy],
                     "up": [dz + dx, dz, dz, 0], "down": [dz + 2 * dx, 0, dz + dx, dz],
                     "south": [2 * dz + dx, dz, 2 * dz + 2 * dx, dz + dy], "north": [dz, dz, dz + dx, dz + dy]}
            element["faces"] = {face: {"uv": [v + (x if j % 2 == 0 else y) for j, v in enumerate(rect)], "texture": texture_index} for face, rect in rects.items()}
            x += width + 2
            row = max(row, height)
        textures.append(texture_record(atlas, "voxel_m%d_p%d.png" % (material, page), args.output))
    report["voxel"] = {"occupied_cells": len(data["cells"]), "cubes_after_merging": len(boxes), "cell_size_bb_units": data["step"],
                       "colour_bits": args.color_bits, "atlas_size": atlas_size, "atlas_pages": len(textures),
                       "texture_approximation": "Nearest surface albedo at voxel centre; flat RGBA per cube; original PNGs also preserved in textures/."}
    report["warnings"].append("Voxel geometry/texture are approximations: curves become cubes, alpha-zero cells are omitted, thin surfaces may expand by a voxel.")
    if len(textures) > 1:
        report["warnings"].append("Multiple cube atlas textures: bbmodel preserves assignments. Bedrock game export needs render-controller/material setup or manual texture atlas consolidation.")
    return elements, owners, textures, atlas_size


def sample_surface_pixels(image, uv):
    """Bilinear repeat sampling, premultiplied alpha to avoid dark fringes."""
    source = np.asarray(image, dtype=np.float32) / 255
    source[:, :, :3] *= source[:, :, 3:4]
    x = (uv[:, 0] % 1) * image.width - 0.5
    y = (1 - (uv[:, 1] % 1)) * image.height - 0.5
    ix, iy = np.floor(x).astype(int), np.floor(y).astype(int)
    fx, fy = (x - ix)[:, None], (y - iy)[:, None]
    top = source[iy % image.height, ix % image.width] * (1 - fx) + source[iy % image.height, (ix + 1) % image.width] * fx
    bottom = source[(iy + 1) % image.height, ix % image.width] * (1 - fx) + source[(iy + 1) % image.height, (ix + 1) % image.width] * fx
    pixels = top * (1 - fy) + bottom * fy
    pixels[:, :3] /= np.maximum(pixels[:, 3:4], 1e-8)
    return np.clip(pixels * 255 + 0.5, 0, 255).astype(np.uint8)


def build_surface_cubes(scene, groups, images, args, work, report):
    data = scene["voxels"]
    surface = data["surface"]
    with np.load(work / surface["samples"]) as samples:
        materials, uvs = samples["material"], samples["uv"]
    pixels = np.zeros((len(materials), 4), dtype=np.uint8)
    sampled_materials = {}
    for material in np.unique(materials):
        if material < 0:
            continue
        mask = materials == material
        pixels[mask] = sample_surface_pixels(images[material], uvs[mask])
        sampled_materials[str(material)] = int(mask.sum())
    boxes = surface["boxes"]
    patches = [(i, face, patch) for i, box in enumerate(boxes) for face, patch in box["faces"].items()]
    edge, positions = pack_rectangles([(p["width"], p["height"]) for _, _, p in patches], args.voxel_atlas_size)
    atlas = Image.new("RGBA", (edge, edge))
    elements, owners = [], []
    for i, box in enumerate(boxes):
        bone = box["bone"]
        lower = np.array(data["origin"]) + np.array(box["start"]) * data["step"]
        upper = lower + np.array(box["size"]) * data["step"]
        elements.append({"name": groups[bone]["name"] + "_surface_" + str(i), "uuid": uid(), "type": "cube",
                         "from": lower.tolist(), "to": upper.tolist(), "origin": groups[bone]["origin"],
                         "rotation": [0, 0, 0], "inflate": 0, "box_uv": False, "autouv": 0,
                         "faces": {f: {"uv": [0, 0, 0, 0], "texture": None} for f in FACE_FRAMES},
                         "visibility": True, "export": True})
        owners.append(bone)
    for (i, face, patch), (x, y) in zip(patches, positions):
        width, height, offset = patch["width"], patch["height"], patch["offset"]
        rgba = pixels[offset:offset + width * height].reshape(height, width, 4)
        # Extrude borders into the packing gutter so filtering cannot pick up
        # another cube's UV island. Interior hidden pixels remain transparent.
        padded = Image.fromarray(np.pad(rgba, ((1, 1), (1, 1), (0, 0)), mode="edge"))
        atlas.paste(padded, (x - 1, y - 1))
        elements[i]["faces"][face] = {"uv": [x, y, x + width, y + height], "texture": 0}
    texture = texture_record(atlas, "voxel_surface.png", args.output)
    report["voxel"] = {"occupied_cells": len(data["cells"]), "cubes_after_merging": len(boxes),
                       "cell_size_bb_units": data["step"], "atlas_size": edge, "atlas_pages": 1,
                       "texture_mode": "surface", "uv_mode": "per_face", "pixels_per_voxel_edge": surface["density"],
                       "visible_cube_faces": len(patches), "sampled_source_materials": sampled_materials,
                       "projection_counts": surface["projection_counts"],
                       "texture_approximation": "Per-texel normal-ray/nearest-surface albedo reprojection; one shared atlas, premultiplied-alpha bilinear sampling and extruded gutters."}
    report["warnings"].append("Voxel curves/thin sheets remain approximations. Surface baking uses Bedrock per-face UV to preserve sub-unit cubes; --voxel-texture flat retains legacy Box UV.")
    return elements, owners, [texture], edge


def build_project(scene, args, work, report):
    material_textures, images = prepare_materials(scene["materials"], work, args.output, args.texture_resolution)
    groups, nodes, outliner = groups_and_outliner(scene["groups"])
    if args.mode == "mesh":
        elements, owners = build_meshes(scene, groups, material_textures, images, report, args.mesh_chunk_faces)
        textures = material_textures
        resolution = max((max(im.size) for im in images), default=16)
    else:
        if scene["voxels"].get("surface"):
            elements, owners, textures, resolution = build_surface_cubes(scene, groups, images, args, work, report)
        else:
            elements, owners, textures, resolution = build_cubes(scene, groups, images, args, report)
    if not elements:
        raise ValueError("No renderable elements remained after conversion")
    for element, bone in zip(elements, owners):
        nodes[bone]["children"].append(element["uuid"])
    animations = []
    for clip in scene["animations"]:
        animators = {}
        for track in clip["tracks"]:
            group = groups[track["group"]]
            keys = []
            for channel, frames in track["channels"].items():
                for frame in frames:
                    keys.append({"uuid": uid(), "channel": channel, "time": frame["time"],
                                 "interpolation": frame["interpolation"],
                                 # Molang treats exponent notation such as 1e-8
                                 # as an expression, not a tiny number. Decimal
                                 # strings prevent spurious multi-unit movement.
                                 "data_points": [dict(zip(("x", "y", "z"), (format(v, ".9f") for v in frame["value"])))]})
            animators[group["uuid"]] = {"name": group["name"], "type": "bone", "rotation_global": False,
                                        "quaternion_interpolation": True, "keyframes": keys}
        animations.append({"uuid": uid(), "name": clip["name"], "loop": clip["loop"], "length": clip["length"],
                           "override": False, "snapping": max(1, round(args.fps)), "animators": animators})
    project = {"meta": {"format_version": "5.0", "model_format": "free" if args.mode == "mesh" else "bedrock", "box_uv": args.mode == "voxel"},
               "name": args.input.stem, "model_identifier": "geometry." + groups[0]["name"],
               "resolution": {"width": resolution, "height": resolution}, "elements": elements, "groups": groups,
               "outliner": outliner, "textures": textures, "animations": animations,
               "animation_variable_placeholders": ""}
    project["meta"]["box_uv"] = args.mode == "voxel" and not scene["voxels"].get("surface")
    (args.output / "validation_checkpoints.json").write_text(json.dumps({"groups": [g["uuid"] for g in groups], "checkpoints": scene["checkpoints"]}, separators=(",", ":")), encoding="utf-8")
    return project

def validate_project(project):
    ids = [g["uuid"] for g in project["groups"]] + [e["uuid"] for e in project["elements"]]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate element/group UUID")
    known = set(ids)
    visited = []
    def visit(nodes):
        for node in nodes:
            identity = node if isinstance(node, str) else node["uuid"]
            if identity not in known:
                raise ValueError("Unknown outliner UUID: " + identity)
            visited.append(identity)
            if isinstance(node, dict):
                visit(node["children"])
    visit(project["outliner"])
    if len(visited) != len(set(visited)) or set(visited) != known:
        raise ValueError("Outliner must contain every group/element exactly once")
    group_ids = {g["uuid"] for g in project["groups"]}
    for element in project["elements"]:
        for face in element["faces"].values():
            if face["texture"] is None:
                continue
            if not isinstance(face["texture"], int) or not 0 <= face["texture"] < len(project["textures"]):
                raise ValueError("Invalid face texture reference")
            if element["type"] == "mesh" and not all(v in element["vertices"] and v in face["uv"] for v in face["vertices"]):
                raise ValueError("Invalid mesh vertex/UV reference")
    for animation in project["animations"]:
        for bone, animator in animation["animators"].items():
            if bone not in group_ids:
                raise ValueError("Invalid animation bone UUID")
            for key in animator["keyframes"]:
                if key["time"] < -1e-8 or key["time"] > animation["length"] + 1e-6:
                    raise ValueError("Animation key outside clip duration")
    json.dumps(project, allow_nan=False)


def bedrock_cube_uv(cube):
    if cube["box_uv"]:
        return cube["uv_offset"]
    faces = {}
    for name, face in cube["faces"].items():
        if face["texture"] is None:
            continue
        u0, v0, u1, v1 = face["uv"]
        if name in {"up", "down"}:
            faces[name] = {"uv": [u1, v1], "uv_size": [u0 - u1, v0 - v1]}
        else:
            faces[name] = {"uv": [u0, v0], "uv_size": [u1 - u0, v1 - v0]}
    return faces


def write_exports(project, args):
    outputs = []
    def write(name, data):
        (args.output / name).write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
        outputs.append(name)
    animations = {}
    for animation in project["animations"]:
        bones = {}
        for animator in animation["animators"].values():
            channels = defaultdict(list)
            for frame in animator["keyframes"]:
                channels[frame["channel"]].append(frame)
            result = {}
            for channel, frames in channels.items():
                values = {}
                previous_step = False
                for frame in sorted(frames, key=lambda f: f["time"]):
                    point = frame["data_points"][0]
                    value = [float(point[k]) for k in ("x", "y", "z")]
                    # Native bbmodel v5 uses viewport coordinates. Bedrock and
                    # GeckoLib use mirrored X position and mirrored X/Y angles.
                    if channel == "position":
                        value[0] *= -1
                    elif channel == "rotation":
                        value[0] *= -1
                        value[1] *= -1
                    value = [0 if abs(v) < 1e-6 else v for v in value]
                    if previous_step and values:
                        prior = list(values.values())[-1]
                        prior = prior["post"] if isinstance(prior, dict) else prior
                        values[format(frame["time"], ".9g")] = {"pre": prior, "post": value}
                    else:
                        values[format(frame["time"], ".9g")] = value
                    previous_step = frame["interpolation"] == "step"
                result[channel] = values
            bones[animator["name"]] = result
        animations["animation." + animation["name"]] = {"animation_length": animation["length"],
            "loop": "hold_on_last_frame" if animation["loop"] == "hold" else animation["loop"] == "loop", "bones": bones}
    if args.bedrock_animation:
        write(args.input.stem + ".animation.json", {"format_version": "1.8.0", "animations": animations})
    if args.geckolib_animation:
        write(args.input.stem + ".geckolib.animation.json", {"format_version": "1.8.0", "animations": animations})
    if args.geo:
        by_id = {g["uuid"]: g for g in project["groups"]}
        elements = {e["uuid"]: e for e in project["elements"]}
        bones = []
        def bone_list(nodes, parent=None):
            for node in nodes:
                if isinstance(node, str):
                    continue
                group = by_id[node["uuid"]]
                bone = {"name": group["name"], "pivot": [-group["origin"][0], *group["origin"][1:]],
                        "rotation": [-group["rotation"][0], -group["rotation"][1], group["rotation"][2]], "cubes": []}
                if parent:
                    bone["parent"] = parent
                for child in node["children"]:
                    if isinstance(child, str):
                        cube = elements[child]
                        bone["cubes"].append({"origin": [-cube["to"][0], cube["from"][1], cube["from"][2]],
                                              "size": [b - a for a, b in zip(cube["from"], cube["to"])],
                                              "uv": bedrock_cube_uv(cube), "inflate": cube["inflate"]})
                bones.append(bone)
                bone_list([c for c in node["children"] if isinstance(c, dict)], group["name"])
        bone_list(project["outliner"])
        bounds = np.array([e[k] for e in project["elements"] for k in ("from", "to")])
        low, high = bounds.min(axis=0), bounds.max(axis=0)
        write(args.input.stem + ".geo.json", {"format_version": "1.12.0", "minecraft:geometry": [{"description": {
            "identifier": project["model_identifier"], "texture_width": project["resolution"]["width"], "texture_height": project["resolution"]["height"],
            "visible_bounds_width": max(high[0] - low[0], high[2] - low[2]) / 16 + 2,
            "visible_bounds_height": (high[1] - low[1]) / 16 + 2, "visible_bounds_offset": [float(-(low[0] + high[0]) / 32), float((low[1] + high[1]) / 32), float((low[2] + high[2]) / 32)]}, "bones": bones}]})
    return outputs
