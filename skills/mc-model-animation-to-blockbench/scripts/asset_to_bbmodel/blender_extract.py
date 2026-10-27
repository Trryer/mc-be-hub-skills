# -*- coding: utf-8 -*-
"""Runs inside Blender only. Smooth skinning is deliberately reduced to rigid groups.

Cuboids approximate a triangulated surface: curved/high-poly assets cannot be
represented losslessly by Minecraft cubes. No vertex weights go into bbmodel.
"""
import json
import math
from pathlib import Path
import re
import sys
import traceback

import bpy
from mathutils import Euler, Matrix, Vector
from mathutils.bvhtree import BVHTree
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from voxel_surface import FACE_FRAMES, face_grid, merge_occupancy


def clean_name(text, fallback, used):
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", text)
    value = re.sub(r"[^a-zA-Z0-9_]+", "_", value).strip("_").lower() or fallback
    if value[0].isdigit():
        value = "bone_" + value
    result, suffix = value, 2
    while result in used:
        result = value + "_" + str(suffix)
        suffix += 1
    used.add(result)
    return result


def action_curves(action):
    result = []
    if hasattr(action, "layers") and len(action.layers):
        for layer in action.layers:
            for strip in layer.strips:
                for bag in getattr(strip, "channelbags", []):
                    result.extend(bag.fcurves)
    else:
        result.extend(action.fcurves)
    return result


def import_asset(cfg):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    path = cfg["input"]
    suffix = Path(path).suffix.lower()
    if cfg.get("fbx_bridge_input"):
        bpy.ops.import_scene.gltf(filepath=cfg["fbx_bridge_input"], import_pack_images=True)
        return
    if suffix == ".fbx":
        bpy.ops.import_scene.fbx(filepath=path, use_anim=True, automatic_bone_orientation=False,
                                 ignore_leaf_bones=False, use_custom_normals=True)
    elif suffix in {".glb", ".gltf"}:
        bpy.ops.import_scene.gltf(filepath=path, import_pack_images=True)
    elif suffix == ".obj":
        if cfg["obj_forward"].removeprefix("NEGATIVE_") == cfg["obj_up"]:
            raise ValueError("OBJ forward and up must be different axes")
        bpy.ops.wm.obj_import(filepath=path, forward_axis=cfg["obj_forward"], up_axis=cfg["obj_up"])


def find_image(socket, visited=None):
    visited = set() if visited is None else visited
    for link in socket.links:
        node = link.from_node
        if node in visited:
            continue
        visited.add(node)
        if node.type == "TEX_IMAGE" and node.image:
            return node.image, link.from_socket.name
        for input_socket in node.inputs:
            image, channel = find_image(input_socket, visited)
            if image:
                return image, channel
    return None, None


def export_materials(work, warnings, source_suffix):
    materials = []
    images = {}
    scene = bpy.context.scene
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "None"
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.image_settings.color_depth = "8"

    def save_image(image):
        if image.name in images:
            return images[image.name]
        # Packed images are lazy-loaded by the glTF importer. Accessing pixels
        # forces decoding before testing has_data, avoiding a false missing PNG.
        if min(image.size) > 0:
            _ = len(image.pixels)
        if not image.has_data or min(image.size) == 0:
            warnings.append("Missing/unreadable image: " + image.name)
            return None
        filename = "image_%03d.png" % len(images)
        image.save_render(str(work / filename), scene=scene)
        images[image.name] = filename
        return filename

    for mat in bpy.data.materials:
        color = list(mat.diffuse_color)
        color_image = alpha_image = None
        alpha_src = None
        alpha_channel = "A"
        bsdf = next((n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None) if mat.use_nodes else None
        if bsdf:
            base = bsdf.inputs["Base Color"]
            alpha = bsdf.inputs["Alpha"]
            color = list(base.default_value)
            color[3] = alpha.default_value
            image, _ = find_image(base)
            if image:
                color_image = save_image(image)
                for node in mat.node_tree.nodes:
                    if node.type == "MAPPING" or (node.type == "UVMAP" and node.uv_map):
                        warnings.append("Material '%s': UV map selection/mapping node is not baked; active mesh UVs retained, inspect texture alignment." % mat.name)
                        break
                if base.links and base.links[0].from_node.type != "TEX_IMAGE":
                    warnings.append("Material '%s': procedural/mixed base-colour graph flattened to its first image; review colour factors." % mat.name)
            alpha_src, channel = find_image(alpha)
            if alpha_src and alpha_src != image:
                alpha_image = save_image(alpha_src)
                alpha_channel = "A" if channel == "Alpha" else "R"
            if image and not alpha.links:
                alpha_channel = "constant"
            elif image and alpha_src == image and channel != "Alpha":
                alpha_image = color_image
                alpha_channel = "R"
        if source_suffix == ".obj" and alpha_src and alpha_channel == "A" and alpha_src.depth in {8, 24}:
            # Blender's OBJ importer connects map_d to Alpha even for grayscale
            # or RGB files without alpha. Such dissolve maps use intensity.
            alpha_image = save_image(alpha_src)
            alpha_channel = "R"
            warnings.append("Material '%s': OBJ dissolve map has no alpha channel; sampled its red/intensity channel." % mat.name)
        materials.append({"name": mat.name, "color": color, "image": color_image,
                          "alpha_image": alpha_image, "alpha_channel": alpha_channel})
    materials.append({"name": "default_material", "color": [0.65, 0.65, 0.65, 1], "image": None,
                      "alpha_image": None, "alpha_channel": "A"})
    return materials


def discover_clips(objects, warnings):
    clips = {}
    seen = set()
    for obj in objects:
        data = obj.animation_data
        if not data:
            continue
        bindings = []
        if data.action:
            bindings.append((data.action.name.split("|")[-1], data.action, getattr(data, "action_slot", None)))
        for track in data.nla_tracks:
            for strip in track.strips:
                if strip.action:
                    name = strip.action.name.split("|")[-1] if track.name.startswith("[") else track.name
                    bindings.append((name, strip.action, getattr(strip, "action_slot", None)))
                    if abs(strip.scale - 1) > 1e-6 or abs(strip.repeat - 1) > 1e-6:
                        warnings.append("NLA '%s': exporting the source clip, not sequencer strip timing/repetition." % name)
        for name, action, slot in bindings:
            identity = (obj.name, action.name, getattr(slot, "identifier", None))
            if identity in seen:
                continue
            seen.add(identity)
            # A currently selected action can also exist in an NLA track. Prefer
            # the track name so glTF multi-object clips stay together.
            other = next((n for n, a, s in bindings[1:] if a == action and s == slot), None)
            if other:
                name = other
            clips.setdefault(name, []).append((obj, action, slot))
    bound = {a for bindings in clips.values() for _, a, _ in bindings}
    for action in bpy.data.actions:
        if action not in bound:
            warnings.append("Unbound action '%s' skipped: no target object/slot could be established." % action.name)
    return clips


def reset_animation(objects, bases):
    for obj in objects:
        if obj.animation_data:
            obj.animation_data.action = None
            for track in obj.animation_data.nla_tracks:
                track.mute = True
        obj.matrix_basis = bases[obj.name].copy()
        if obj.type == "ARMATURE":
            obj.data.pose_position = "POSE"
            for bone in obj.pose.bones:
                bone.matrix_basis.identity()
    bpy.context.view_layer.update()


def collect_groups(objects):
    groups, lookup, bones = [], {}, {}
    used = set()
    # Parents precede children, including parented-to-bone objects.
    def add_object(obj):
        if obj.name in lookup:
            return lookup[obj.name]
        parent = add_object(obj.parent) if obj.parent else None
        if obj.parent and obj.parent_type == "BONE":
            parent = bones.get((obj.parent.name, obj.parent_bone), parent)
        idx = len(groups)
        lookup[obj.name] = idx
        groups.append({"name": clean_name(obj.name, "node", used), "source": obj.name,
                       "parent": parent, "kind": "object", "rest": obj.matrix_world.copy(), "object": obj})
        if obj.type == "ARMATURE":
            def add_bone(bone):
                key = (obj.name, bone.name)
                if key in bones:
                    return bones[key]
                p = add_bone(bone.parent) if bone.parent else idx
                bi = len(groups)
                bones[key] = bi
                groups.append({"name": clean_name(bone.name, "bone", used), "source": bone.name,
                               "parent": p, "kind": "bone", "rest": obj.matrix_world @ bone.matrix_local,
                               "object": obj, "bone": bone.name})
                return bi
            for bone in obj.data.bones:
                add_bone(bone)
        return idx
    for obj in objects:
        add_object(obj)
    return groups, lookup, bones


def collect_meshes(objects, lookup, bones, warnings, cfg):
    meshes = []
    material_ids = {m.name: i for i, m in enumerate(bpy.data.materials)}
    depsgraph = bpy.context.evaluated_depsgraph_get()
    blended, total_weighted = 0, 0
    original_triangles = sum(sum(max(0, len(p.vertices) - 2) for p in o.data.polygons) for o in objects if o.type == "MESH")
    for obj in objects:
        if obj.type != "MESH":
            continue
        arm_mods = [m for m in obj.modifiers if m.type == "ARMATURE" and m.object]
        if len(arm_mods) > 1:
            warnings.append("Mesh '%s': multiple armature modifiers; only the first provides rigid weight assignment." % obj.name)
        arm = arm_mods[0].object if arm_mods else (obj.parent if obj.parent and obj.parent.type == "ARMATURE" else None)
        states = [(m, m.show_viewport) for m in arm_mods]
        for mod, _ in states:
            mod.show_viewport = False
        bpy.context.view_layer.update()
        evaluated = obj.evaluated_get(depsgraph)
        mesh = evaluated.to_mesh(preserve_all_data_layers=True, depsgraph=depsgraph)
        mesh.calc_loop_triangles()
        vertices = [list(obj.matrix_world @ v.co) for v in mesh.vertices]
        weights = []
        for vertex in mesh.vertices:
            entries = {}
            if arm:
                for item in vertex.groups:
                    if item.group < len(obj.vertex_groups):
                        bi = bones.get((arm.name, obj.vertex_groups[item.group].name))
                        if bi is not None and item.weight > 1e-6:
                            entries[bi] = item.weight
            weights.append(entries)
            total_weighted += bool(entries)
            blended += len(entries) > 1
        uv_layer = mesh.uv_layers.active
        if uv_layer is None:
            warnings.append("Mesh '%s' has no UVs; assigning [0,0] / material colour." % obj.name)
        tris = []
        for triangle in mesh.loop_triangles:
            score = {}
            for vi in triangle.vertices:
                for bone, weight in weights[vi].items():
                    score[bone] = score.get(bone, 0) + weight
            bone = max(score, key=score.get) if score else lookup[obj.name]
            material = mesh.materials[triangle.material_index] if triangle.material_index < len(mesh.materials) else None
            uvs = [list(uv_layer.data[li].uv) for li in triangle.loops] if uv_layer else [[0, 0]] * 3
            if not all(math.isfinite(x) for uv in uvs for x in uv):
                warnings.append("Mesh '%s': non-finite UV replaced with [0,0]." % obj.name)
                uvs = [[0, 0]] * 3
            tris.append({"v": list(triangle.vertices), "uv": uvs, "bone": bone,
                         "material": material_ids[material.name] if material else len(bpy.data.materials)})
        if obj.matrix_world.to_3x3().determinant() < 0:
            for tri in tris:
                tri["v"][1], tri["v"][2] = tri["v"][2], tri["v"][1]
                tri["uv"][1], tri["uv"][2] = tri["uv"][2], tri["uv"][1]
        meshes.append({"name": obj.name, "vertices": vertices, "triangles": tris})
        evaluated.to_mesh_clear()
        for mod, state in states:
            mod.show_viewport = state
        if obj.data.shape_keys:
            warnings.append("Mesh '%s': morph/shape-key animation is not exported; current basis geometry only." % obj.name)
    if blended:
        warnings.append("%d/%d weighted vertices have multiple influences; each triangle uses its strongest summed bone (rigid approximation)." % (blended, total_weighted))
    return meshes, {"weighted_vertices": total_weighted, "blended_vertices": blended, "original_triangles": original_triangles}


def normalise(meshes, groups, cfg):
    # Blender importers already understand FBX/glTF axis metadata. Only Blender's
    # Z-up -> BB Y-up is applied here, not another source-file axis correction.
    rotation = Matrix(((1, 0, 0, 0), (0, 0, 1, 0), (0, -1, 0, 0), (0, 0, 0, 1)))
    points = [rotation @ Vector(v) for mesh in meshes for v in mesh["vertices"]]
    if not points:
        raise ValueError("No mesh vertices found")
    array = np.array(points)
    if not np.isfinite(array).all():
        raise ValueError("Mesh contains non-finite vertex coordinates")
    low, high = array.min(axis=0), array.max(axis=0)
    extent = float(max(high - low))
    if extent <= 1e-12:
        raise ValueError("Model bounds are degenerate")
    scale = cfg["scale"] if cfg["scale"] is not None else cfg["fit_size"] / extent
    shift = Vector((0, 0, 0)) if cfg["no_center"] else Vector((-(low[0] + high[0]) / 2, -low[1], -(low[2] + high[2]) / 2))
    transform = Matrix.Diagonal((scale, scale, scale, 1)) @ Matrix.Translation(shift) @ rotation
    for mesh in meshes:
        mesh["vertices"] = [list(transform @ Vector(v)) for v in mesh["vertices"]]
    for group in groups:
        world = transform @ group["rest"]
        location, quaternion, rest_scale = world.decompose()
        # Keep each joint's rest orientation instead of flattening all bones to
        # world axes. Otherwise rotated non-uniform scale becomes artificial
        # shear, which a single BB group cannot represent.
        group["frame"] = Matrix.LocRotScale(location, quaternion, Vector((1, 1, 1)))
        parent = group["parent"]
        local = groups[parent]["frame"].inverted() @ group["frame"] if parent is not None else group["frame"]
        group["pivot"] = list(local.translation + Vector(groups[parent]["pivot"])) if parent is not None else list(local.translation)
        group["rotation"] = [math.degrees(v) for v in local.to_quaternion().to_euler("XYZ")]
        group["world_to_local"] = [list(row) for row in group["frame"].inverted()]
    return transform, {"axis": "Blender (x,y,z) -> Blockbench (x,z,-y); importer handles source metadata",
                       "bb_units_per_blender_metre": scale, "offset_before_scale": list(shift),
                       "source_bounds_y_up": [low.tolist(), high.tolist()], "bb_longest_edge": extent * scale,
                       "rotation_order": "BB intrinsic ZYX == Blender extrinsic XYZ"}


def bake_animations(clips, objects, bases, groups, transform, cfg, warnings):
    animations, checkpoints, interpolation_sources = [], [], {}
    fps = bpy.context.scene.render.fps / bpy.context.scene.render.fps_base
    inverse = transform.inverted()
    max_shear = 0.0
    for name, bindings in clips.items():
        reset_animation(objects, bases)
        starts, ends, raw_frames, curves = [], [], [], []
        for obj, action, slot in bindings:
            data = obj.animation_data_create()
            data.action = action
            if slot:
                data.action_slot = slot
            start, end = action.frame_range
            starts.append(float(start))
            ends.append(float(end))
            curves.extend(action_curves(action))
        start, end = min(starts), max(ends)
        duration = max(0, (end - start) / fps)
        times = {0.0, duration}
        times.update(min(i / cfg["fps"], duration) for i in range(math.ceil(duration * cfg["fps"]) + 1))
        for curve in curves:
            for key in curve.keyframe_points:
                times.add(max(0, min(duration, (float(key.co.x) - start) / fps)))
        times = sorted(times)
        interpolation_sources[name] = sorted({k.interpolation for curve in curves for k in curve.keyframe_points})
        if any(i not in {"LINEAR", "CONSTANT"} for i in interpolation_sources[name]):
            warnings.append("Animation '%s': cubic/Bezier curves sampled at %s fps plus source key times; output uses linear/slerp." % (name, cfg["fps"]))
        previous = [None] * len(groups)

        def sample(time):
            nonlocal max_shear
            frame = start + time * fps
            bpy.context.scene.frame_set(math.floor(frame), subframe=frame - math.floor(frame))
            world = []
            for group in groups:
                obj = group["object"]
                pose = obj.matrix_world @ obj.pose.bones[group["bone"]].matrix if group["kind"] == "bone" else obj.matrix_world
                deformation = transform @ pose @ group["rest"].inverted() @ inverse
                world.append(deformation @ group["frame"])
            result = []
            for i, group in enumerate(groups):
                parent = group["parent"]
                local = world[parent].inverted() @ world[i] if parent is not None else world[i]
                location, quaternion, scale = local.decompose()
                # mathutils' XYZ extrinsic matrix equals THREE/Blockbench ZYX.
                euler = quaternion.to_euler("XYZ", previous[i]) if previous[i] else quaternion.to_euler("XYZ")
                previous[i] = euler.copy()
                base = Vector(group["pivot"])
                if parent is not None:
                    base -= Vector(groups[parent]["pivot"])
                rebuilt = Matrix.LocRotScale(location, quaternion, scale)
                max_shear = max(max_shear, max(abs(local[r][c] - rebuilt[r][c]) for r in range(4) for c in range(4)))
                result.append({"position": list(location - base), "rotation": [math.degrees(a) - b for a, b in zip(euler, group["rotation"])], "scale": list(scale)})
            return result, world

        samples, worlds = [], []
        for time in times:
            values, matrices = sample(time)
            samples.append(values)
            worlds.append(matrices)
        # Determine STEP per output channel from actual intermediate transforms.
        # This also works after coordinate/bone-axis changes and parent motion.
        midpoints = [sample((a + b) / 2)[0] for a, b in zip(times, times[1:])]
        tracks = []
        for gi, group in enumerate(groups):
            channels = {}
            for channel in ("position", "rotation", "scale"):
                keys = []
                for ti, time in enumerate(times):
                    value = samples[ti][gi][channel]
                    interpolation = "linear"
                    if ti + 1 < len(times):
                        middle = midpoints[ti][gi][channel]
                        after = samples[ti + 1][gi][channel]
                        if max(abs(a - b) for a, b in zip(value, middle)) < 1e-5 and max(abs(a - b) for a, b in zip(value, after)) > 1e-5:
                            interpolation = "step"
                    keys.append({"time": time, "value": value, "interpolation": interpolation})
                neutral = [1, 1, 1] if channel == "scale" else [0, 0, 0]
                if any(max(abs(a - b) for a, b in zip(k["value"], neutral)) > 1e-5 for k in keys):
                    channels[channel] = keys
            if channels:
                tracks.append({"group": gi, "channels": channels})
        loop = cfg["loop"]
        if loop == "auto":
            explicit = next((action.get("loop") for _, action, _ in bindings if "loop" in action), None)
            cyclic = any(m.type == "CYCLES" for c in curves for m in c.modifiers)
            guessed = any(word in name.lower() for word in ("idle", "walk", "run", "loop"))
            loop = "loop" if (explicit is True or cyclic or (explicit is None and guessed)) else "once"
            if explicit is None and not cyclic:
                warnings.append("Animation '%s': no portable loop metadata; inferred '%s' from clip name. Override with --loop." % (name, loop))
        animations.append({"name": name, "length": duration, "loop": loop, "tracks": tracks})
        for ti in sorted({0, len(times) // 2, len(times) - 1}):
            checkpoints.append({"clip": name, "time": times[ti], "groups": [
                {"group": i, "matrix": [float(worlds[ti][i][r][c]) for c in range(4) for r in range(4)]} for i in range(len(groups))]})
    reset_animation(objects, bases)
    if max_shear > 1e-4:
        warnings.append("Animation non-uniform-scale/shear decomposition residual %.6g; rigid TRS cannot preserve shear exactly." % max_shear)
    return animations, checkpoints, {"source_interpolations": interpolation_sources, "max_trs_residual": max_shear,
                                      "sample_fps": cfg["fps"], "source_fps": fps}


def barycentric(point, a, b, c):
    v0, v1, v2 = b - a, c - a, point - a
    d00, d01, d11 = v0.dot(v0), v0.dot(v1), v1.dot(v1)
    denom = d00 * d11 - d01 * d01
    if abs(denom) < 1e-18:
        return [1, 0, 0]
    v = (d11 * v2.dot(v0) - d01 * v2.dot(v1)) / denom
    w = (d00 * v2.dot(v1) - d01 * v2.dot(v0)) / denom
    return [1 - v - w, v, w]


def voxelise(meshes, groups, cfg, warnings):
    # A near-surface shell keeps open/thin meshes visible. Paired scan-line hits
    # fill closed regions. This is an approximation, not an exact solid CAD test.
    buckets = {}
    for mesh in meshes:
        vertices = [Vector(v) for v in mesh["vertices"]]
        for tri in mesh["triangles"]:
            group = groups[tri["bone"]]
            inverse = group["frame"].inverted()
            offset = Vector(group["pivot"])
            points = [inverse @ vertices[v] + offset for v in tri["v"]]
            buckets.setdefault(tri["bone"], []).append((points, tri))
    all_points = np.array([v for mesh in meshes for v in mesh["vertices"]])
    minimum = np.array([v for tris in buckets.values() for points, _ in tris for v in points]).min(axis=0)
    step = float(np.ptp(all_points, axis=0).max() / cfg["voxel_resolution"])
    grid_origin = np.floor(minimum / step) * step
    result, odd_columns = [], 0
    surface_boxes, surface_materials, surface_uvs = [], [], []
    projection_counts = {"ray": 0, "nearest": 0, "hidden": 0}
    cell_budget = cfg.get("max_voxel_cells", 4000000)
    for bone, triangles in buckets.items():
        verts = [v for points, _ in triangles for v in points]
        tree = BVHTree.FromPolygons(verts, [(i * 3, i * 3 + 1, i * 3 + 2) for i in range(len(triangles))], all_triangles=True)
        bounds = np.array(verts)
        low = np.floor((bounds.min(axis=0) - grid_origin) / step).astype(int)
        high = np.ceil((bounds.max(axis=0) - grid_origin) / step).astype(int)
        high = np.maximum(high, low + 1)
        if math.prod(int(n) for n in high-low) > cell_budget * 8:
            raise ValueError("Voxel grid bounding volume exceeds the scan budget; lower --voxel-resolution or explicitly raise --max-voxel-cells")
        direction = Vector((0, 0, 1))
        for ix in range(int(low[0]), int(high[0])):
            for iy in range(int(low[1]), int(high[1])):
                x, y = grid_origin[:2] + (np.array([ix, iy]) + 0.5) * step
                z0 = float(grid_origin[2] + (low[2] - 1) * step)
                zmax = float(grid_origin[2] + (high[2] + 1) * step)
                hits = []
                ray = Vector((x, y, z0))
                for _ in range(len(triangles) + 1):
                    hit, _, face, _ = tree.ray_cast(ray, direction, zmax - ray.z)
                    if hit is None:
                        break
                    if not hits or hit.z - hits[-1] > step * 1e-5:
                        hits.append(hit.z)
                    ray.z = hit.z + step * 1e-5
                    if ray.z >= zmax:
                        break
                odd_columns += len(hits) % 2
                for iz in range(int(low[2]), int(high[2])):
                    point = Vector((x, y, float(grid_origin[2] + (iz + 0.5) * step)))
                    nearest, _, face, distance = tree.find_nearest(point)
                    if nearest is None:
                        continue
                    inside = any(a <= point.z <= b for a, b in zip(hits[::2], hits[1::2]))
                    if distance > step * 0.65 and not inside:
                        continue
                    points, tri = triangles[face]
                    weights = barycentric(nearest, *points)
                    uv = [sum(weights[j] * tri["uv"][j][axis] for j in range(3)) for axis in range(2)]
                    result.append({"cell": [ix, iy, iz], "bone": bone, "material": tri["material"], "uv": uv})
                    if len(result) > cell_budget:
                        raise ValueError("Voxel occupancy exceeds --max-voxel-cells; lower --voxel-resolution or explicitly raise the budget")
        print("Voxelised bone %s: %s cumulative cells" % (bone, len(result)), flush=True)
        if cfg.get("voxel_texture", "surface") == "surface":
            occupied = {tuple(v["cell"]) for v in result if v["bone"] == bone}
            boxes = merge_occupancy(occupied)
            if len(surface_boxes) + len(boxes) > cfg["max_cubes"]:
                raise ValueError("Merged voxel cubes exceed --max-cubes; lower --voxel-resolution")
            bake_surface_boxes(boxes, occupied, tree, triangles, bone, grid_origin, step,
                               cfg["voxel_texture_density"], surface_boxes, surface_materials, surface_uvs, projection_counts)
            print("Baked bone %s: %s cumulative cuboids" % (bone, len(surface_boxes)), flush=True)
    if odd_columns:
        warnings.append("Voxelisation: %d scan columns have unpaired intersections (open/non-manifold surfaces); surface shell retained." % odd_columns)
    if cfg.get("voxel_texture", "surface") == "surface":
        samples = Path(cfg["work"]) / "surface_samples.npz"
        if not surface_materials:
            raise ValueError("Voxelisation produced no visible surface; increase --voxel-resolution")
        np.savez_compressed(samples, material=np.concatenate(surface_materials), uv=np.concatenate(surface_uvs))
        return {"cells": result, "step": step, "origin": grid_origin.tolist(), "odd_columns": odd_columns,
                "surface": {"boxes": surface_boxes, "samples": samples.name, "density": cfg["voxel_texture_density"],
                            "projection_counts": projection_counts}}
    return {"cells": result, "step": step, "origin": grid_origin.tolist(), "odd_columns": odd_columns}


def bake_surface_boxes(boxes, occupied, tree, triangles, bone, grid_origin, step,
                       density, records, material_arrays, uv_arrays, counts):
    offset = sum(len(a) for a in material_arrays)
    for start, size in boxes:
        record = {"bone": bone, "start": start, "size": size, "faces": {}}
        for face in FACE_FRAMES:
            grid, normal = face_grid(start, size, face, density)
            height, width = grid.shape[:2]
            indices = np.full((height * width,), -1, dtype=np.int32)
            uvs = np.zeros((height * width, 2), dtype=np.float32)
            n = Vector(normal)
            for index, sample in enumerate(grid.reshape(-1, 3)):
                neighbour = tuple(np.floor(sample + normal * 0.0001).astype(int))
                if neighbour in occupied:
                    counts["hidden"] += 1
                    continue
                point = Vector(grid_origin + sample * step)
                # Nearby directional projection maintains coherent UVs across a
                # large merged face. Nearest-surface fallback handles silhouettes
                # and open sheets where a normal ray misses the original mesh.
                hit, hit_normal, face_index, distance = tree.ray_cast(point + n * (step * 0.85), -n, step * 1.7)
                if hit is not None and hit_normal.dot(n) > 0.08:
                    counts["ray"] += 1
                else:
                    hit, _, face_index, distance = tree.find_nearest(point)
                    counts["nearest"] += 1
                if hit is None:
                    continue
                vertices, triangle = triangles[face_index]
                weights = barycentric(hit, *vertices)
                indices[index] = triangle["material"]
                uvs[index] = [sum(weights[j] * triangle["uv"][j][axis] for j in range(3)) for axis in range(2)]
            if np.any(indices >= 0):
                record["faces"][face] = {"offset": offset, "width": width, "height": height}
                offset += len(indices)
                material_arrays.append(indices)
                uv_arrays.append(uvs)
        # Entirely enclosed boxes do not contribute a visible surface.
        if record["faces"]:
            records.append(record)


def run(cfg):
    work = Path(cfg["work"])
    warnings = []
    import_asset(cfg)
    widgets = {b.custom_shape for o in bpy.context.scene.objects if o.type == "ARMATURE" for b in o.pose.bones if b.custom_shape}
    objects = [o for o in bpy.context.scene.objects if o not in widgets]
    clips = discover_clips(objects, warnings)
    bases = {o.name: o.matrix_basis.copy() for o in objects}
    reset_animation(objects, bases)
    groups, lookup, bones = collect_groups(objects)
    meshes, skin_report = collect_meshes(objects, lookup, bones, warnings, cfg)
    if not bones and not cfg.get("fbx_bridge_input"):
        warnings.append("Source has no armature bones; object hierarchy is kept as rigid groups (static input is valid).")
    if not clips:
        warnings.append("Source has no bound animation clips; no animation was invented.")
    if any(o.constraints for o in objects) or any(b.constraints for o in objects if o.type == "ARMATURE" for b in o.pose.bones):
        warnings.append("Constraints are evaluated and baked at sample times, not exported as editable constraints.")
    if any(len(o.data.uv_layers) > 1 for o in objects if o.type == "MESH"):
        warnings.append("Multiple UV sets detected: only the active UV set is exported.")
    materials = export_materials(work, warnings, Path(cfg["input"]).suffix.lower())
    if cfg.get("albedo"):
        image = bpy.data.images.load(cfg["albedo"], check_existing=True)
        if min(image.size) <= 0:
            raise ValueError("Albedo override cannot be decoded: " + cfg["albedo"])
        image.save_render(str(work / "albedo_override.png"), scene=bpy.context.scene)
        for material in materials:
            material.update(color=[1, 1, 1, 1], image="albedo_override.png", alpha_image=None, alpha_channel="A")
        warnings.append("Explicit --albedo replaces all source material base colours; original per-corner UV and supplied alpha are retained.")
    transform, transforms = normalise(meshes, groups, cfg)
    animations, checkpoints, anim_report = bake_animations(clips, objects, bases, groups, transform, cfg, warnings)
    voxels = voxelise(meshes, groups, cfg, warnings) if cfg["mode"] == "voxel" else None
    serial_groups = [{k: v for k, v in group.items() if k in {"name", "source", "parent", "kind", "pivot", "rotation", "world_to_local"}} for group in groups]
    scene = {"groups": serial_groups, "meshes": meshes, "materials": materials, "animations": animations,
             "voxels": voxels, "checkpoints": checkpoints,
             "report": {"warnings": list(dict.fromkeys(warnings)), "blender_version": bpy.app.version_string,
                        "source_counts": {"meshes": len(meshes), "vertices": sum(len(m["vertices"]) for m in meshes),
                                          "triangles": sum(len(m["triangles"]) for m in meshes), "bones": len(bones),
                                          "materials": len(materials) - 1, "clips": len(clips)},
                        "skin": skin_report, "transforms": transforms, "animation": anim_report,
                        "bone_names": [{"source": g["source"], "target": g["name"]} for g in groups]}}
    (work / "scene.json").write_text(json.dumps(scene, separators=(",", ":"), allow_nan=False), encoding="utf-8")


if __name__ == "__main__":
    config = json.loads(Path(sys.argv[sys.argv.index("--") + 1]).read_text(encoding="utf-8"))
    try:
        run(config)
    except Exception as error:
        # Importers/files/third-party animation data can fail. Preserve their
        # traceback rather than hiding an official API error and continuing.
        (Path(config["work"]) / "diagnostics.json").write_text(json.dumps({"warnings": [], "error": str(error)}), encoding="utf-8")
        traceback.print_exc()
        raise
