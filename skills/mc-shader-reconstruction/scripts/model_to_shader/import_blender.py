"""Blender 4.5 adapter: GLB/glTF, OBJ and binary FBX -> versioned NPZ."""
import json
from pathlib import Path
import sys
sys.dont_write_bytecode = True
import traceback
import bpy
from mathutils import Matrix
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parent))
from common import save_scene,write_json,srgb

def run(cfg):
    work = Path(cfg['work'])
    bpy.ops.wm.read_factory_settings(use_empty=True)
    path = cfg['input']
    suffix = Path(path).suffix.lower()
    if suffix in ('.glb','.gltf'):
        bpy.ops.import_scene.gltf(filepath=path,import_pack_images=True)
    elif suffix=='.fbx':
        bpy.ops.import_scene.fbx(filepath=path,use_anim=True,use_custom_normals=True)
    elif suffix=='.obj':
        bpy.ops.wm.obj_import(filepath=path,forward_axis=cfg['obj_forward'],up_axis=cfg['obj_up'])
    else:
        raise ValueError('Unsupported Blender input: '+suffix)
    warnings = []
    animated = [a.name for a in bpy.data.actions]
    if animated and cfg.get('pose_frame') is None:
        raise ValueError('Animation detected %s; select --pose-frame explicitly. This pipeline exports one pose, not animation.'%animated)
    if cfg.get('pose_frame') is not None:
        bpy.context.scene.frame_set(int(cfg['pose_frame']),subframe=cfg['pose_frame']%1)
        warnings.append('Explicit snapshot at Blender frame %s; clips are not exported'%cfg['pose_frame'])
    for obj in bpy.data.objects:
        if obj.type=='ARMATURE' and cfg.get('pose_frame') is None:
            obj.data.pose_position='REST'
    bpy.context.view_layer.update()
    axis = np.array([[1,0,0],[0,0,1],[0,-1,0]],dtype=float)
    materials,lookup = [],{}
    override = cfg.get('albedo')
    mapping = cfg.get('material_map',{})
    def material(mat):
        key = mat.name if mat else '__default__'
        if key in lookup:
            return lookup[key]
        record = dict(name=key,color=[.65,.65,.65,1.],image=None,wrap='repeat')
        image = None
        explicit = mapping.get(key,override)
        if mat and not explicit:
            record['color'] = list(srgb(mat.diffuse_color[:3]))+[float(mat.diffuse_color[3])]
            if mat.use_nodes:
                output = next((n for n in mat.node_tree.nodes if n.type=='OUTPUT_MATERIAL' and n.is_active_output),None)
                surface = output.inputs['Surface'] if output else None
                bsdf = surface.links[0].from_node if surface and surface.is_linked else None
                if not bsdf or bsdf.type!='BSDF_PRINCIPLED':
                    raise ValueError('Unsupported material shader: '+key)
                base,alpha = bsdf.inputs['Base Color'],bsdf.inputs['Alpha']
                record['color'] = list(srgb(base.default_value[:3]))+[float(alpha.default_value)]
                if base.is_linked:
                    node = base.links[0].from_node
                    # Standard glTF BaseColorFactor imports as a constant multiply.
                    if node.type=='MIX' and node.data_type=='RGBA' and node.blend_type=='MULTIPLY':
                        a,b = node.inputs[6],node.inputs[7]
                        if node.inputs[0].is_linked or abs(node.inputs[0].default_value-1)>1e-6 or a.is_linked==b.is_linked:
                            raise ValueError('Unsupported color mixing: '+key)
                        linked,constant = (a,b) if a.is_linked else (b,a)
                        record['texture_factor_linear'] = list(constant.default_value[:3])
                        node = linked.links[0].from_node
                    if node.type!='TEX_IMAGE' or not node.image:
                        raise ValueError('Base Color must be a direct image or constant: '+key)
                    image = node.image
                    record['color'][:3] = [1.,1.,1.]
                    if node.inputs['Vector'].is_linked:
                        link = node.inputs['Vector'].links[0]
                        if link.from_node.type=='UVMAP':
                            record['uv_layer'] = link.from_node.uv_map
                        elif link.from_node.type!='TEX_COORD' or link.from_socket.name!='UV':
                            raise ValueError('Non-UV coordinate or UV transform requires baking first: '+key)
                    if node.extension not in ('REPEAT','EXTEND','MIRROR'):
                        raise ValueError('Unsupported texture wrap: '+node.extension)
                    record['wrap'] = {'REPEAT':'repeat','EXTEND':'clamp','MIRROR':'mirror'}[node.extension]
                if alpha.is_linked:
                    link = alpha.links[0]
                    opacity_image = link.from_node.image if link.from_node.type=='TEX_IMAGE' else None
                    if (not opacity_image or link.from_socket.name!='Alpha' or not len(opacity_image.pixels)
                            or np.asarray(opacity_image.pixels)[3::4].min()<.999):
                        raise ValueError('Transparent/separate/procedural alpha requires a dedicated path: '+key)
                if bsdf.inputs['Emission Color'].is_linked or bsdf.inputs['Emission Strength'].default_value>0:
                    warnings.append('Emission is not reproduced: '+key)
                if bsdf.inputs['Normal'].is_linked:
                    warnings.append('Normal/bump image is not reproduced: '+key)
        index = len(materials)
        if explicit:
            # Explicit user override uses file RGB directly and original UVs.
            from PIL import Image
            target = work/('image_%03d.png'%index)
            with Image.open(explicit) as im:
                im.convert('RGBA').save(target)
            record.update(image=target.name,color=[1.,1.,1.,1.])
        elif image:
            if min(image.size)<=0 or len(image.pixels)==0:
                raise ValueError('Missing/unreadable texture: '+image.name)
            target = work/('image_%03d.png'%index)
            scene = bpy.context.scene
            scene.view_settings.view_transform='Standard'
            scene.view_settings.look='None'
            scene.render.image_settings.file_format='PNG'
            scene.render.image_settings.color_mode='RGBA'
            scene.render.image_settings.color_depth='8'
            image.save_render(str(target),scene=scene)
            record['image'] = target.name
        lookup[key] = index
        materials.append(record)
        return index
    vertices,faces,normals,uvs,ids = [],[],[],[],[]
    offset = 0
    nodes = []
    graph = bpy.context.evaluated_depsgraph_get()
    for obj in bpy.context.scene.objects:
        if obj.instance_type!='NONE':
            raise ValueError('Realize collection/particle instances before import: '+obj.name)
        if obj.type!='MESH':
            continue
        evaluated = obj.evaluated_get(graph)
        mesh = evaluated.to_mesh(preserve_all_data_layers=True,depsgraph=graph)
        mesh.calc_loop_triangles()
        matrix = np.array(evaluated.matrix_world,dtype=float)
        transform = axis@matrix[:3,:3]
        if np.linalg.cond(transform)>1e12:
            raise ValueError('Singular object transform: '+obj.name)
        raw = np.array([tuple(v.co) for v in mesh.vertices])
        if not len(raw):
            evaluated.to_mesh_clear()
            continue
        world = raw@transform.T+axis@matrix[:3,3]
        vertices.extend(world.tolist())
        normal_matrix = np.linalg.inv(transform)
        corner_normals = mesh.corner_normals
        for tri in mesh.loop_triangles:
            mat = mesh.materials[tri.material_index] if tri.material_index<len(mesh.materials) else None
            mi = material(mat)
            uv_name = materials[mi].get('uv_layer')
            layer = mesh.uv_layers.get(uv_name) if uv_name else mesh.uv_layers.active
            if materials[mi]['image'] and not layer:
                raise ValueError('Textured mesh has no UV: '+obj.name)
            order = [0,2,1] if np.linalg.det(transform)<0 else [0,1,2]
            faces.append([offset+tri.vertices[i] for i in order])
            normals.append([(np.array(corner_normals[tri.loops[i]].vector)@normal_matrix).tolist() for i in order])
            uvs.append([list(layer.data[tri.loops[i]].uv) if layer else [0,0] for i in order])
            ids.append(mi)
        offset += len(raw)
        nodes.append(dict(name=obj.name,matrix_world=matrix.tolist(),triangles=len(mesh.loop_triangles)))
        evaluated.to_mesh_clear()
    unknown = set(mapping)-set(lookup)
    if unknown:
        raise ValueError('Unknown --material-map names: '+str(sorted(unknown)))
    save_scene(work,vertices,faces,normals,uvs,ids,materials,
               dict(reader='Blender '+bpy.app.version_string,nodes=nodes,animation_clips=animated,
                    warnings=warnings,material_scope='Base color and geometry normals; PBR/alpha/morph playback not exported'))

if __name__=='__main__':
    cfg = json.loads(Path(sys.argv[sys.argv.index('--')+1]).read_text(encoding='utf-8'))
    try:
        run(cfg)
    except Exception as error:
        write_json(Path(cfg['work'])/'import_error.json',dict(error=str(error),traceback=traceback.format_exc()))
        raise
