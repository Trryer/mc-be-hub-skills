# -*- coding: utf-8 -*-
"""Run in Blender: blender -b --python make_test_glb.py -- OUTPUT.glb"""
from pathlib import Path
import json
import struct
import sys

import bpy
from mathutils import Vector


def create_fixture(output):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.scene.render.fps = 30
    armature = bpy.data.armatures.new("TestRig")
    rig = bpy.data.objects.new("TestRig", armature)
    bpy.context.collection.objects.link(rig)
    bpy.context.view_layer.objects.active = rig
    rig.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    root = armature.edit_bones.new("Root主骨")
    root.head, root.tail = (0, 0, 0), (0.15, 0, 1)
    tip = armature.edit_bones.new("Upper.Arm")
    tip.head, tip.tail = (0.15, 0, 1), (0.5, 0.2, 2)
    tip.parent = root
    bpy.ops.object.mode_set(mode="OBJECT")
    rig.rotation_euler = (0.15, -0.22, 0.31)
    rig.scale = (1.2, 1.2, 1.2)
    materials = []
    for name, colour in [("red_opaque", (0.8, 0.1, 0.1, 1)), ("blue_alpha", (0.1, 0.3, 0.9, 0.45))]:
        material = bpy.data.materials.new(name)
        material.use_nodes = True
        principled = material.node_tree.nodes.get("Principled BSDF")
        principled.inputs["Base Color"].default_value = colour
        principled.inputs["Alpha"].default_value = colour[3]
        material.surface_render_method = "DITHERED"
        materials.append(material)
    for part, z in enumerate((0.5, 1.5)):
        bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, z))
        obj = bpy.context.object
        obj.name = "TestPart_%d" % part
        obj.scale = (0.4, 0.3, 0.5)
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        obj.data.materials.append(materials[part])
        # One image with true transparent texels, exported embedded into GLB.
        if part == 1:
            image = bpy.data.images.new("alpha_checker", width=4, height=4, alpha=True)
            image.pixels[:] = [c for y in range(4) for x in range(4) for c in (0.2, 0.5, 0.9, 0.0 if (x + y) % 2 else 0.7)]
            node = materials[part].node_tree.nodes.new("ShaderNodeTexImage")
            node.image = image
            bsdf = materials[part].node_tree.nodes.get("Principled BSDF")
            materials[part].node_tree.links.new(node.outputs["Color"], bsdf.inputs["Base Color"])
            materials[part].node_tree.links.new(node.outputs["Alpha"], bsdf.inputs["Alpha"])
        obj.parent = rig
        modifier = obj.modifiers.new("Skin", "ARMATURE")
        modifier.object = rig
        for bone_name in ("Root主骨", "Upper.Arm"):
            obj.vertex_groups.new(name=bone_name)
        obj.vertex_groups[part].add(list(range(len(obj.data.vertices))), 0.8, "REPLACE")
        obj.vertex_groups[1 - part].add(list(range(len(obj.data.vertices))), 0.2, "REPLACE")
    clips = [("idle", [(1, 0, 0), (16, 0.15, 0.3), (31, 0, 0)]),
             ("attack", [(1, 0, 0), (8, 0.5, -1), (16, 0, 0)])]
    for name, frames in clips:
        action = bpy.data.actions.new(name)
        action["loop"] = name == "idle"
        rig.animation_data_create().action = action
        for frame, position, angle in frames:
            rig.pose.bones["Root主骨"].location = (position, 0, 0)
            rig.pose.bones["Root主骨"].keyframe_insert("location", frame=frame)
            rig.pose.bones["Upper.Arm"].rotation_mode = "XYZ"
            rig.pose.bones["Upper.Arm"].rotation_euler = (0, angle, 0.2 * angle)
            rig.pose.bones["Upper.Arm"].keyframe_insert("rotation_euler", frame=frame)
            rig.pose.bones["Upper.Arm"].scale = (1, 1, 1 + position * 0.2)
            rig.pose.bones["Upper.Arm"].keyframe_insert("scale", frame=frame)
        slot = rig.animation_data.action_slot
        track = rig.animation_data.nla_tracks.new()
        track.name = name
        strip = track.strips.new(name, 1, action)
        if slot:
            strip.action_slot = slot
        track.mute = True
        rig.animation_data.action = None
    for bone in rig.pose.bones:
        bone.matrix_basis.identity()
    bpy.context.scene.frame_set(1)
    output.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.export_scene.gltf(filepath=str(output), export_format="GLB", export_animations=True,
                             export_animation_mode="NLA_TRACKS", export_force_sampling=True,
                             export_nla_strips_merged_animation_name="Animation", export_extras=True)
    # glTF export bakes Blender F-curves. Make one actual STEP sampler in the
    # resulting GLB to test source interpolation, not just its visual appearance.
    data = output.read_bytes()
    length = struct.unpack_from("<I", data, 12)[0]
    document = json.loads(data[20:20 + length])
    for animation in document["animations"]:
        if animation["name"] == "attack":
            for channel in animation["channels"]:
                if channel["target"]["path"] == "translation":
                    animation["samplers"][channel["sampler"]]["interpolation"] = "STEP"
    payload = json.dumps(document, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    payload += b" " * (-len(payload) % 4)
    remainder = data[20 + length:]
    output.write_bytes(struct.pack("<III", 0x46546C67, 2, 20 + len(payload) + len(remainder)) + struct.pack("<II", len(payload), 0x4E4F534A) + payload + remainder)
    print("Fixture:", output)


if __name__ == "__main__":
    create_fixture(Path(sys.argv[sys.argv.index("--") + 1]).resolve())
