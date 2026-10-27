"""Isolated ufbx 0.0.5 adapter; binary and triangulated ASCII FBX."""
from io import BytesIO
import json
import os
from pathlib import Path
import sys
import traceback
import numpy as np
from PIL import Image
import ufbx
from common import save_scene,write_json,srgb

KEEP = []
def keep(value):
    KEEP.append(value)
    return value
def items(value):
    keep(value)
    return [keep(value[i]) for i in range(len(value))]

def run(cfg):
    source,work = Path(cfg['input']),Path(cfg['work'])
    scene = keep(ufbx.load_file(str(source),target_axes=ufbx.axes_right_handed_y_up,
                               target_unit_meters=1.,load_external_files=False))
    warnings = []
    curves = items(scene.anim_curves)
    stacks = items(scene.anim_stacks)
    clips = [dict(name=s.name,start=s.time_begin,end=s.time_end) for s in stacks]
    if curves and cfg.get('pose_frame') is None:
        raise ValueError('FBX has animation curves; use --pose-frame and optional --clip for an explicit static snapshot')
    snapshot = cfg.get('pose_frame') is not None
    if snapshot:
        if not stacks:
            raise ValueError('--pose-frame requested but FBX has no clip')
        selected = [s for s in stacks if not cfg.get('clip') or s.name==cfg['clip']]
        if len(selected)!=1:
            raise ValueError('Select one --clip from '+str([s.name for s in stacks]))
        seconds = selected[0].time_begin+cfg['pose_frame']/cfg['pose_fps']
        if seconds>selected[0].time_end or seconds<selected[0].time_begin:
            raise ValueError('Snapshot is outside selected FBX clip')
        scene = keep(ufbx.evaluate_scene(scene,keep(selected[0].anim),seconds,evaluate_skinning=True))
        warnings.append('Static evaluated/skinned snapshot at %.6fs; animation clips not exported'%seconds)
    materials,lookup = [],{}
    mapping = cfg.get('material_map',{})
    def material(mat):
        name = mat.name if mat else '__default__'
        if name in lookup:
            return lookup[name]
        index = len(materials)
        record = dict(name=name,color=[.65,.65,.65,1.],image=None,wrap='repeat')
        texture = None
        if mat:
            fbx,pbr = keep(mat.fbx),keep(mat.pbr)
            diffuse = keep(pbr.base_color)
            if not diffuse.has_value and not keep(diffuse.texture):
                diffuse = keep(fbx.diffuse_color)
            if diffuse.has_value:
                record['color'][:3] = list(srgb(list(diffuse.value_vec4)[:3]))
            texture = keep(diffuse.texture)
            transparency = keep(fbx.transparency_factor)
            if transparency.has_value and transparency.value_vec4[0]>.001:
                raise ValueError('Transparent FBX material unsupported: '+name)
        override = mapping.get(name,cfg.get('albedo'))
        payload = None
        if override:
            payload = Path(override).read_bytes()
            record['color'] = [1.,1.,1.,1.]
        elif texture:
            if texture.has_uv_transform:
                raise ValueError('FBX UV transform must be baked first: '+name)
            if len(items(texture.layers)):
                raise ValueError('Layered FBX texture requires material baking: '+name)
            record['wrap'] = 'repeat' if texture.wrap_u==ufbx.WrapMode.REPEAT else 'clamp'
            if texture.wrap_u!=texture.wrap_v:
                raise ValueError('Mixed-axis texture wrap needs an adapter: '+name)
            payload = texture.content
            if not payload:
                paths = [Path(texture.absolute_filename),source.parent/texture.relative_filename,
                         source.parent/Path(texture.filename.replace('\\','/')).name]
                found = next((p for p in paths if p.is_file()),None)
                if found:
                    payload = found.read_bytes()
            if not payload:
                raise ValueError('Missing FBX albedo texture: '+texture.filename)
        if payload:
            with Image.open(BytesIO(payload)) as image:
                image.convert('RGBA').save(work/('image_%03d.png'%index))
            record['image'] = 'image_%03d.png'%index
            # Match Blender's FBX Base Color interpretation: connected RGB
            # texture replaces DiffuseColor; the constant is used without one.
            record['color'] = [1.,1.,1.,1.]
        lookup[name] = index
        materials.append(record)
        return index
    vertices,faces,normals,uvs,ids,nodes = [],[],[],[],[],[]
    offset = 0
    for mesh in items(scene.meshes):
        native_faces = items(mesh.faces)
        if any(f.num_indices!=3 for f in native_faces):
            raise ValueError('ufbx adapter requires triangular FBX; binary FBX may use --reader blender to triangulate')
        indices = np.asarray(list(keep(mesh.vertex_indices)),dtype='u4')
        uv = keep(mesh.vertex_uv)
        corner_uv = (np.asarray(list(keep(uv.values)))[np.asarray(list(keep(uv.indices)),dtype='u4')]
                     if uv.exists else np.zeros((len(indices),2)))
        fm = np.asarray(list(keep(mesh.face_material)),dtype='i4')
        if not len(fm):
            fm = np.zeros(len(native_faces),dtype='i4')
        for node in items(mesh.instances):
            transform = np.asarray(node.geometry_to_world,dtype=float).T
            if np.linalg.cond(transform[:,:3])>1e12:
                raise ValueError('Singular FBX transform: '+node.name)
            skinned = snapshot and len(items(mesh.skin_deformers))>0
            pos = keep(mesh.skinned_position) if skinned else None
            world_positions = skinned and not mesh.skinned_is_local
            if pos and pos.exists:
                corner = np.asarray(list(keep(pos.values)))[np.asarray(list(keep(pos.indices)),dtype='u4')]
            else:
                corner = np.asarray(list(keep(mesh.vertices)))[indices]
            if not world_positions:
                corner = corner@transform[:,:3].T+transform[:,3]
            normal = keep(mesh.skinned_normal) if skinned else keep(mesh.vertex_normal)
            if normal.exists:
                cn = np.asarray(list(keep(normal.values)))[np.asarray(list(keep(normal.indices)),dtype='u4')]
                if not world_positions:
                    cn = cn@np.linalg.inv(transform[:,:3])
            else:
                tri = corner.reshape(-1,3,3)
                cn = np.repeat(np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]),3,axis=0)
            node_materials = items(node.materials)
            mapped = []
            for index in fm:
                mi = material(node_materials[index] if 0<=index<len(node_materials) else None)
                if materials[mi]['image'] and not uv.exists:
                    raise ValueError('Textured FBX mesh has no UV: '+node.name)
                mapped.append(mi)
            local_faces = np.arange(len(corner),dtype='u4').reshape(-1,3)
            ct,nt = corner_uv.reshape(-1,3,2),cn.reshape(-1,3,3)
            if np.linalg.det(transform[:,:3])<0:
                # ufbx world-space evaluated skin normals include the reflection
                # orientation. Restore outward normals as well as winding.
                if world_positions:
                    nt = -nt
                local_faces = local_faces[:,[0,2,1]]
                ct,nt = ct[:,[0,2,1]],nt[:,[0,2,1]]
            vertices.extend(corner.tolist())
            faces.extend((local_faces+offset).tolist())
            normals.extend(nt.tolist())
            uvs.extend(ct.tolist())
            ids.extend(mapped)
            offset += len(corner)
            nodes.append(dict(name=node.name,geometry_to_world=transform.tolist(),triangles=len(native_faces)))
    if set(mapping)-set(lookup):
        raise ValueError('Unknown material-map names: '+str(set(mapping)-set(lookup)))
    save_scene(work,vertices,faces,normals,uvs,ids,materials,
               dict(reader='ufbx 0.0.5',nodes=nodes,animation_clips=clips,animation_curves=len(curves),
                    warnings=warnings,material_scope='Base color + normals; full PBR and animation playback not exported'))

if __name__=='__main__':
    cfg = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
    code = 0
    try:
        run(cfg)
    except Exception as error:
        write_json(Path(cfg['work'])/'import_error.json',dict(error=str(error),traceback=traceback.format_exc()))
        code = 1
    sys.stdout.flush()
    sys.stderr.flush()
    # ufbx Windows wrappers can crash in native finalizers. The extraction is
    # isolated; keep wrappers alive until all interchange files are flushed.
    os._exit(code)
