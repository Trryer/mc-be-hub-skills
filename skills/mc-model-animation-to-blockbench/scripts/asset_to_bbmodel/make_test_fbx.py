# -*- coding: utf-8 -*-
"""Blender: --python make_test_fbx.py -- INPUT.glb OUTPUT.fbx"""
from pathlib import Path
import sys

import bpy


def main():
    source, output = [str(Path(p).resolve()) for p in sys.argv[sys.argv.index("--") + 1:]]
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=source)
    for obj in bpy.context.scene.objects:
        if obj.animation_data:
            obj.animation_data.action = None
            for track in obj.animation_data.nla_tracks:
                track.mute = False
        if obj.type == "MESH":
            bpy.context.view_layer.objects.active = obj
            modifier = obj.modifiers.new("fbx_bridge_triangulate", "TRIANGULATE")
            bpy.ops.object.modifier_apply(modifier=modifier.name)
    bpy.ops.export_scene.fbx(filepath=output, object_types={"MESH", "ARMATURE", "EMPTY"},
                             use_mesh_modifiers=True, add_leaf_bones=False,
                             bake_anim=True, bake_anim_use_nla_strips=True,
                             bake_anim_use_all_actions=False, bake_anim_simplify_factor=0,
                             path_mode="COPY", embed_textures=True)


if __name__ == "__main__":
    main()
