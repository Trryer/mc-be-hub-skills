# -*- coding: utf-8 -*-
"""Isolated ufbx -> rigid GLB bridge. No skin weights are written to bbmodel.

Run with Python 3.11 + numpy + ufbx==0.0.5 (Blender's bundled Python works).
The intermediate GLB attaches each triangle to its strongest summed bone.
Smooth blended joints are therefore approximate; later voxelisation also
approximates curved surfaces. This is not a lossless skinned-model exporter.
"""
import json
import math
import os
from pathlib import Path
import struct
import sys

import numpy as np
import ufbx

# ufbx 0.0.5's Windows wrappers must survive until the isolated process exits.
KEEP = []


def keep(value):
    KEEP.append(value)
    return value


def native_list(value):
    keep(value)
    return [keep(value[i]) for i in range(len(value))]


def matrix(value):
    result = np.eye(4)
    result[:3] = np.asarray(value, dtype=float).T
    return result


def trs(value):
    return {"translation": list(value.translation), "rotation": list(value.rotation), "scale": list(value.scale)}


class Glb:
    def __init__(self):
        self.data = {"asset": {"version": "2.0", "generator": "asset_to_bbmodel ufbx rigid bridge"},
                     "scene": 0, "scenes": [{"nodes": []}], "nodes": [], "meshes": [],
                     "materials": [], "bufferViews": [], "accessors": [], "animations": []}
        self.binary = bytearray()

    def view(self, data):
        self.binary.extend(b"\x00" * (-len(self.binary) % 4))
        index = len(self.data["bufferViews"])
        self.data["bufferViews"].append({"buffer": 0, "byteOffset": len(self.binary), "byteLength": len(data)})
        self.binary.extend(data)
        return index

    def accessor(self, array, kind, bounds=False):
        array = np.asarray(array, dtype="<u4" if kind == "SCALAR_UINT" else "<f4")
        if not np.isfinite(array).all():
            raise ValueError("FBX contains non-finite geometry/animation data")
        record = {"bufferView": self.view(array.tobytes()), "componentType": 5125 if kind == "SCALAR_UINT" else 5126,
                  "count": len(array), "type": "SCALAR" if kind == "SCALAR_UINT" else kind}
        if bounds:
            record.update(min=np.atleast_1d(array.min(axis=0)).tolist(), max=np.atleast_1d(array.max(axis=0)).tolist())
        index = len(self.data["accessors"])
        self.data["accessors"].append(record)
        return index

    def save(self, path):
        self.binary.extend(b"\x00" * (-len(self.binary) % 4))
        self.data["buffers"] = [{"byteLength": len(self.binary)}]
        payload = json.dumps(self.data, separators=(",", ":"), allow_nan=False).encode("utf-8")
        payload += b" " * (-len(payload) % 4)
        with path.open("wb") as stream:
            stream.write(struct.pack("<III", 0x46546C67, 2, 28 + len(payload) + len(self.binary)))
            stream.write(struct.pack("<II", len(payload), 0x4E4F534A))
            stream.write(payload)
            stream.write(struct.pack("<II", len(self.binary), 0x004E4942))
            stream.write(self.binary)


def export_material(material, source, glb, warnings):
    diffuse = keep(keep(material.fbx).diffuse_color)
    color = list(diffuse.value_vec4)[:3] if diffuse.has_value else [.65] * 3
    record = {"name": material.name, "doubleSided": True, "alphaMode": "BLEND",
              "pbrMetallicRoughness": {"baseColorFactor": color + [1], "metallicFactor": 0}}
    texture = keep(diffuse.texture)
    if texture:
        content = texture.content
        if not content:
            paths = [Path(texture.absolute_filename), source.parent / texture.relative_filename,
                     source.parent / Path(texture.filename).name]
            found = next((p for p in paths if p.is_file()), None)
            if found:
                content = found.read_bytes()
        if content:
            mime = "image/png" if content[:8] == b"\x89PNG\r\n\x1a\n" else "image/jpeg" if content[:2] == b"\xff\xd8" else None
            if mime:
                images = glb.data.setdefault("images", [])
                textures = glb.data.setdefault("textures", [])
                images.append({"bufferView": glb.view(content), "mimeType": mime})
                textures.append({"source": len(images) - 1})
                record["pbrMetallicRoughness"]["baseColorTexture"] = {"index": len(textures) - 1}
            else:
                warnings.append("FBX material '%s': bridge supports embedded PNG/JPEG only; convert its albedo to PNG and use --albedo." % material.name)
        else:
            warnings.append("FBX material '%s': missing texture '%s'." % (material.name, texture.filename))
    return record


def bridge(cfg):
    source, work = Path(cfg["input"]), Path(cfg["work"])
    scene = keep(ufbx.load_file(str(source), target_axes=ufbx.axes_right_handed_y_up,
                               target_unit_meters=1.0, load_external_files=False,
                               inherit_mode_handling=ufbx.InheritModeHandling.HELPER_NODES))
    nodes = native_list(scene.nodes)
    glb, warnings = Glb(), []
    node_index = {n.typed_id: i for i, n in enumerate(nodes)}
    for node in nodes:
        record = dict(name=node.name or "fbx_scene", **trs(node.local_transform))
        record["children"] = [node_index[n.typed_id] for n in native_list(node.children)]
        glb.data["nodes"].append(record)
        if not keep(node.parent):
            glb.data["scenes"][0]["nodes"].append(node_index[node.typed_id])
    materials = native_list(scene.materials)
    glb.data["materials"] = [export_material(m, source, glb, warnings) for m in materials]
    default_material = len(materials)
    glb.data["materials"].append({"name": "default_material", "pbrMetallicRoughness": {"baseColorFactor": [.65, .65, .65, 1]}})
    weighted, blended, triangles_total = 0, 0, 0
    for mesh in native_list(scene.meshes):
        # This binding does not expose ufbx_triangulate_face. Reject rather than
        # silently fan-triangulating concave polygons and corrupting their UVs.
        if mesh.num_indices != mesh.num_faces * 3 or any(f.num_indices != 3 for f in keep(mesh.faces)):
            raise ValueError("ufbx bridge requires triangulated FBX meshes; triangulate in the DCC or use the Blender reader for binary FBX")
        raw = np.asarray(list(keep(mesh.vertices)), dtype=float)
        corners = np.asarray(list(keep(mesh.vertex_indices)), dtype=np.uint32).reshape(-1, 3)
        uv_attr = keep(mesh.vertex_uv)
        if uv_attr.exists:
            uv = np.asarray(list(keep(uv_attr.values)), dtype=float)
            uvi = np.asarray(list(keep(uv_attr.indices)), dtype=np.uint32).reshape(-1, 3)
        else:
            warnings.append("FBX mesh '%s' has no UVs; using [0,0]." % mesh.name)
            uv, uvi = np.zeros((1, 2)), np.zeros_like(corners)
        skin = native_list(mesh.skin_deformers)
        if len(skin) > 1:
            raise ValueError("ufbx bridge supports one skin deformer per mesh")
        clusters = native_list(skin[0].clusters) if skin else []
        weights = np.zeros((len(raw), len(clusters)), dtype=np.float32)
        for ci, cluster in enumerate(clusters):
            indices = np.asarray(list(keep(cluster.vertices)), dtype=np.uint32)
            weights[indices, ci] = list(keep(cluster.weights))
        weighted += int(np.count_nonzero(weights.sum(axis=1) > 1e-6))
        blended += int(np.count_nonzero((weights > 1e-6).sum(axis=1) > 1))
        if clusters:
            scores = sum(weights[corners[:, axis]] for axis in range(3))
            owners = scores.argmax(axis=1)
            owners[scores.max(axis=1) <= 1e-6] = len(clusters)
        else:
            owners = np.zeros(len(corners), dtype=int)
        face_material = np.asarray(list(keep(mesh.face_material)), dtype=int)
        if len(face_material) == 0:
            face_material = np.zeros(len(corners), dtype=int)
        for instance in native_list(mesh.instances):
            instance_materials = native_list(instance.materials)
            for owner in np.unique(owners):
                cluster = clusters[int(owner)] if owner < len(clusters) else None
                bone = keep(cluster.bone_node) if cluster else instance
                if bone is None:
                    raise ValueError("FBX skin cluster has no bone node")
                geometry = matrix(cluster.geometry_to_bone if cluster else instance.geometry_to_node)
                positions = raw @ geometry[:3, :3].T + geometry[:3, 3]
                primitives = []
                for mi in np.unique(face_material[owners == owner]):
                    selected = (owners == owner) & (face_material == mi)
                    pairs = np.stack((corners[selected].reshape(-1), uvi[selected].reshape(-1)), axis=1)
                    unique, inverse = np.unique(pairs, axis=0, return_inverse=True)
                    # glTF stores texture-coordinate V from the top; FBX uses bottom.
                    mapped_uv = uv[unique[:, 1]].copy()
                    mapped_uv[:, 1] = 1 - mapped_uv[:, 1]
                    face_indices = inverse.reshape(-1, 3)
                    if np.linalg.det(geometry[:3, :3]) < 0:
                        face_indices = face_indices[:, [0, 2, 1]]
                    mat = instance_materials[int(mi)].typed_id if 0 <= mi < len(instance_materials) else default_material
                    primitives.append({"attributes": {"POSITION": glb.accessor(positions[unique[:, 0]], "VEC3", True),
                                                       "TEXCOORD_0": glb.accessor(mapped_uv, "VEC2")},
                                       "indices": glb.accessor(face_indices.reshape(-1), "SCALAR_UINT"), "material": mat})
                mesh_index = len(glb.data["meshes"])
                glb.data["meshes"].append({"name": mesh.name, "primitives": primitives})
                child = len(glb.data["nodes"])
                glb.data["nodes"].append({"name": mesh.name + "_rigid_" + str(owner), "mesh": mesh_index})
                glb.data["nodes"][node_index[bone.typed_id]]["children"].append(child)
            triangles_total += len(corners)
        if len(keep(mesh.blend_deformers)):
            warnings.append("FBX mesh '%s': morph animation is not exported." % mesh.name)
    if blended:
        warnings.append("ufbx rigid bridge: %d/%d weighted vertices have blended influences; triangles use strongest summed bone, no smooth skin weights." % (blended, weighted))
    all_curves = native_list(scene.anim_curves)
    raw_keys = {float(k.time) for curve in all_curves for k in keep(curve.keyframes)}
    step_edges = set()
    for curve in all_curves:
        keys = list(keep(curve.keyframes))
        for before, after in zip(keys, keys[1:]):
            if before.interpolation in (ufbx.Interpolation.CONSTANT_PREV, ufbx.Interpolation.CONSTANT_NEXT):
                edge = after.time if before.interpolation == ufbx.Interpolation.CONSTANT_PREV else before.time
                step_edges.add(float(edge))
    source_interpolations = sorted({ufbx.Interpolation(k.interpolation).name for curve in all_curves for k in keep(curve.keyframes)})
    clips_report = []
    for stack in native_list(scene.anim_stacks):
        anim = keep(stack.anim)
        start, end = stack.time_begin, stack.time_end
        length = max(0, end - start)
        times = {0.0, length}
        times.update(min(i / cfg["fps"], length) for i in range(math.ceil(length * cfg["fps"]) + 1))
        times.update(t - start for t in raw_keys if start <= t <= end)
        # glTF has one interpolation type per sampler. A mixed STEP/continuous
        # FBX channel is baked with a sub-microsecond transition around each
        # discontinuity instead of smearing a jump across the full 1/fps frame.
        for edge in step_edges:
            relative = edge - start
            if 0 <= relative <= length:
                anchor = np.float32(relative)
                before = min(relative - 1e-7, float(np.nextafter(anchor, np.float32(-np.inf))))
                after = max(relative + 1e-7, float(np.nextafter(anchor, np.float32(np.inf))))
                times.update(t for t in (before, after) if 0 <= t <= length)
        # glTF timestamps are float32: deduplicate after conversion, so nearby
        # source keys cannot become invalid equal-time sampler entries.
        times = np.unique(np.asarray(sorted(times), dtype=np.float32)).astype(float)
        animation = {"name": stack.name or "fbx_animation", "samplers": [], "channels": []}
        time_accessor = glb.accessor(times, "SCALAR", True)
        for index, node in enumerate(nodes):
            samples = [trs(ufbx.evaluate_transform(anim, node, float(start + t))) for t in times]
            for channel, kind in (("translation", "VEC3"), ("rotation", "VEC4"), ("scale", "VEC3")):
                values = np.array([sample[channel] for sample in samples])
                if channel == "rotation":
                    for i in range(1, len(values)):
                        if np.dot(values[i - 1], values[i]) < 0:
                            values[i] *= -1
                rest = glb.data["nodes"][index][channel]
                if np.max(np.abs(values - rest)) < 1e-8:
                    continue
                sampler = len(animation["samplers"])
                animation["samplers"].append({"input": time_accessor, "output": glb.accessor(values, kind), "interpolation": "LINEAR"})
                animation["channels"].append({"sampler": sampler, "target": {"node": index, "path": channel}})
        if not animation["channels"]:
            # Retain a static clip and its duration rather than dropping it.
            values = np.tile(glb.data["nodes"][0]["translation"], (len(times), 1))
            animation["samplers"].append({"input": time_accessor, "output": glb.accessor(values, "VEC3")})
            animation["channels"].append({"sampler": 0, "target": {"node": 0, "path": "translation"}})
        glb.data["animations"].append(animation)
        clips_report.append({"name": animation["name"], "length": length, "samples": len(times)})
    warnings.append("ufbx bridge samples evaluated FBX transforms at --fps plus source key times; output is linear/quaternion interpolation, not original curve handles or portable loop flags.")
    if step_edges:
        warnings.append("FBX STEP edges use short float32-representable bracketing in the GLB bridge; mixed interpolation is an approximation, not original editable STEP handles.")
    glb.save(work / "fbx_rigid.glb")
    report = {"reader": "ufbx 0.0.5 -> rigid GLB -> Blender", "source_meshes": len(keep(scene.meshes)),
              "source_bones": len(keep(scene.bones)), "triangles": triangles_total,
              "weighted_vertices": weighted, "blended_vertices": blended,
              "source_interpolations": source_interpolations, "clips": clips_report, "warnings": warnings}
    (work / "fbx_bridge.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    bridge(json.loads(Path(sys.argv[1]).read_text(encoding="utf-8")))
    sys.stdout.flush()
    sys.stderr.flush()
    # Only this isolated third-party parser process uses an immediate exit.
    os._exit(0)
