"""Blender-only regression fixtures, generated locally; no project assets required."""
import json
from pathlib import Path
import sys
import bpy
from mathutils import Vector

def main(folder):
    out = Path(folder).resolve()
    if out.exists() and any(out.iterdir()):
        raise ValueError('Fixture directory must be new/empty')
    out.mkdir(parents=True,exist_ok=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    im = bpy.data.images.new('asymmetric_uv',width=64,height=64,alpha=True)
    pixels = []
    for y in range(64):
        for x in range(64):
            pixels.extend((.15+.75*(x>=32),.2+.65*(y>=32),.1+.7*(x//16==y//16),1.))
    im.pixels = pixels
    im.filepath_raw = str(out/'albedo.png')
    im.file_format = 'PNG'
    im.save()
    texture = bpy.data.materials.new('texture_uv')
    texture.use_nodes = True
    bsdf = texture.node_tree.nodes.get('Principled BSDF')
    node = texture.node_tree.nodes.new('ShaderNodeTexImage')
    node.image = im
    uv = texture.node_tree.nodes.new('ShaderNodeUVMap')
    uv.uv_map = 'UVMap'
    texture.node_tree.links.new(uv.outputs['UV'],node.inputs['Vector'])
    texture.node_tree.links.new(node.outputs['Color'],bsdf.inputs['Base Color'])
    solid = bpy.data.materials.new('solid_blue')
    solid.use_nodes = True
    solid.node_tree.nodes.get('Principled BSDF').inputs['Base Color'].default_value = (.03,.12,.7,1)
    parent = bpy.data.objects.new('parent_transform',None)
    bpy.context.collection.objects.link(parent)
    parent.location = (.3,-.2,.1)
    parent.rotation_euler = (.07,-.11,.23)
    meshes = []
    bpy.ops.mesh.primitive_cube_add(size=1,location=(-.65,0,.7))
    cube = bpy.context.object
    cube.name = 'multimaterial_box'
    cube.scale = (.7,.8,1.4)
    cube.data.materials.append(texture)
    cube.data.materials.append(solid)
    for face in cube.data.polygons:
        face.material_index = face.index%2
    meshes.append(cube)
    bpy.ops.mesh.primitive_uv_sphere_add(segments=24,ring_count=12,radius=.48,location=(.55,.12,.8))
    sphere = bpy.context.object
    sphere.name = 'negative_nonuniform_sphere'
    sphere.scale = (-1,.8,1.2)
    sphere.data.materials.append(texture)
    for poly in sphere.data.polygons:
        poly.use_smooth = True
    meshes.append(sphere)
    bpy.ops.mesh.primitive_cylinder_add(vertices=24,radius=.18,depth=1.2,location=(.2,.1,1.5))
    bar = bpy.context.object
    bar.name = 'crossbar'
    bar.rotation_euler = (0,1.57079632679,0)
    bar.data.materials.append(solid)
    meshes.append(bar)
    for obj in meshes:
        obj.parent = parent
        modifier = obj.modifiers.new('triangulate','TRIANGULATE')
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.modifier_apply(modifier=modifier.name)
    bpy.ops.export_scene.gltf(filepath=str(out/'fixture.glb'),export_format='GLB')
    bpy.ops.export_scene.gltf(filepath=str(out/'fixture.gltf'),export_format='GLTF_SEPARATE')
    factor = json.loads((out/'fixture.gltf').read_text())
    for mat in factor['materials']:
        if mat['name']=='texture_uv':
            mat['pbrMetallicRoughness']['baseColorFactor'] = [.4,.8,.6,1.]
    (out/'factor.gltf').write_text(json.dumps(factor),encoding='utf-8')
    bpy.ops.wm.obj_export(filepath=str(out/'fixture.obj'),forward_axis='NEGATIVE_Z',up_axis='Y')
    bpy.ops.export_scene.fbx(filepath=str(out/'fixture.fbx'),bake_anim=False,path_mode='COPY',embed_textures=True)
    missing = json.loads((out/'fixture.gltf').read_text())
    for image in missing.get('images',[]):
        image['uri'] = 'definitely_missing_albedo.png'
    (out/'missing_texture.gltf').write_text(json.dumps(missing),encoding='utf-8')
    # Two bones plus an Armature modifier: the snapshot test must deform geometry.
    bpy.ops.object.armature_add(location=(0,0,0))
    arm = bpy.context.object
    arm.name = 'snapshot_rig'
    bpy.ops.object.mode_set(mode='EDIT')
    root = arm.data.edit_bones[0]
    root.name = 'root'
    root.head,root.tail = (0,0,0),(0,0,.5)
    tip = arm.data.edit_bones.new('tip')
    tip.head,tip.tail = root.tail,(0,0,2)
    tip.parent = root
    bpy.ops.object.mode_set(mode='OBJECT')
    for obj in meshes:
        group = obj.vertex_groups.new(name='tip')
        group.add(list(range(len(obj.data.vertices))),1.,'REPLACE')
        mod = obj.modifiers.new('skin','ARMATURE')
        mod.object = arm
    bone = arm.pose.bones['tip']
    bone.rotation_mode = 'XYZ'
    bone.rotation_euler = (0,0,0)
    bone.keyframe_insert('rotation_euler',frame=1)
    bone.rotation_euler = (0,.55,0)
    bone.keyframe_insert('rotation_euler',frame=21)
    arm.animation_data.action.name = 'bend'
    bpy.context.scene.frame_start,bpy.context.scene.frame_end = 1,21
    bpy.context.scene.render.fps = 30
    bpy.context.scene.frame_set(1)
    bpy.ops.export_scene.fbx(filepath=str(out/'animated.fbx'),bake_anim=True,bake_anim_use_all_actions=False,
                             bake_anim_use_nla_strips=False,path_mode='COPY',embed_textures=True,add_leaf_bones=False)
    bpy.ops.export_scene.gltf(filepath=str(out/'animated.glb'),export_format='GLB')
    # A declared alpha surface and a UV-free textured OBJ exercise hard failures.
    alpha = json.loads((out/'fixture.gltf').read_text())
    alpha['materials'][0]['alphaMode'] = 'BLEND'
    alpha['materials'][0].setdefault('pbrMetallicRoughness',{})['baseColorFactor'] = [1,1,1,.5]
    (out/'alpha.gltf').write_text(json.dumps(alpha),encoding='utf-8')
    obj_text = (out/'fixture.obj').read_text()
    lines = []
    for line in obj_text.splitlines():
        if line.startswith('vt '):
            continue
        if line.startswith('f '):
            line = 'f '+' '.join(v.split('/')[0]+'//'+v.split('/')[-1] for v in line[2:].split())
        lines.append(line)
    (out/'no_uv.obj').write_text('\n'.join(lines),encoding='utf-8')
    (out/'broken.glb').write_bytes(b'glTF broken input')
    print('Regression assets ready:',out,flush=True)

if __name__=='__main__':
    main(sys.argv[sys.argv.index('--')+1])
