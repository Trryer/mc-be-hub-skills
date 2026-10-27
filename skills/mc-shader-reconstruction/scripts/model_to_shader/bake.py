"""Generic mesh -> padded 2D distance/material atlases. Offline Open3D."""
import math
from pathlib import Path
import time
import numpy as np
from PIL import Image
import open3d as o3d
from common import load_scene,surface,write_json,digest

def oct_encode(n):
    n = n/np.maximum(np.abs(n).sum(1,keepdims=True),1e-12)
    xy = n[:,:2].copy()
    lower = n[:,2]<0
    xy[lower] = (1-np.abs(xy[lower,::-1]))*np.where(xy[lower]>=0,1,-1)
    return np.rint((xy*.5+.5)*255).clip(0,255).astype('u1')

def bake(work,out,resolution,steps,threads,max_mib,max_atlas,shell):
    start = time.perf_counter()
    mesh,info,textures = load_scene(work)
    bounds = np.asarray(info['model_bounds'])
    pitch = 2./(resolution-9)
    cells = np.ceil((bounds[1]-bounds[0])/pitch-1e-4).astype('i4')+9
    origin = bounds[0]-4*pitch
    nx,ny,nz = map(int,cells)
    columns = math.ceil(math.sqrt(nz*(ny+2)/(nx+2)))
    width,height = columns*(nx+2),math.ceil(nz/columns)*(ny+2)
    gpu_bytes = width*height*8
    if max(width,height)>max_atlas or gpu_bytes>max_mib*1024**2:
        raise ValueError('Atlas budget exceeded: %dx%d, %.2f MiB; select a lower resolution or explicitly raise budget'
                         %(width,height,gpu_bytes/1024**2))
    scene = o3d.t.geometry.RaycastingScene(nthreads=threads)
    scene.add_triangles(o3d.core.Tensor(mesh['vertices'],dtype=o3d.core.Dtype.Float32),
                        o3d.core.Tensor(mesh['faces'],dtype=o3d.core.Dtype.UInt32))
    # Occupancy signs require a closed mesh; open meshes use a surface shell.
    legacy = o3d.geometry.TriangleMesh(o3d.utility.Vector3dVector(mesh['vertices'].astype(float)),
                                     o3d.utility.Vector3iVector(mesh['faces'].astype('i4')))
    legacy.remove_duplicated_vertices()
    watertight = legacy.is_watertight()
    field = np.zeros((height,width,4),dtype='u1')
    material = np.zeros_like(field)
    x,y = np.meshgrid(np.arange(nx,dtype='f4'),np.arange(ny,dtype='f4'))
    base = np.column_stack([x.ravel(),y.ravel(),np.zeros(nx*ny,dtype='f4')])
    distance_range = max(.12,6*pitch)
    for z in range(nz):
        points = base.copy()
        points[:,2] = z
        points = (points*pitch+origin).astype('f4')
        query = o3d.core.Tensor(points)
        nearest = scene.compute_closest_points(query,nthreads=threads)
        unsigned = np.linalg.norm(points-nearest['points'].numpy(),axis=1)
        distance = unsigned.copy()
        if watertight:
            inside = scene.compute_occupancy(query,nthreads=threads,nsamples=3).numpy()>.5
            distance[inside] *= -1
        distance = np.minimum(distance,unsigned-shell*pitch)
        code = np.rint((np.clip(distance/distance_range,-1,1)*.5+.5)*65535).astype('u2')
        layer = np.zeros((nx*ny,4),dtype='u1')
        layer[:,0],layer[:,1] = code>>8,code&255
        colors = np.zeros_like(layer)
        band = np.abs(distance)<5*pitch
        ids = nearest['primitive_ids'].numpy()[band]
        bary = nearest['primitive_uvs'].numpy()[band]
        color,normal = surface(mesh,info,textures,ids,bary)
        layer[band,2:] = oct_encode(normal)
        colors[band,:3] = np.rint(color*255).clip(0,255).astype('u1')
        colors[:,3] = 255
        row,column = divmod(z,columns)
        ys,xs = row*(ny+2),column*(nx+2)
        for target,values in ((field,layer),(material,colors)):
            target[ys:ys+ny+2,xs:xs+nx+2] = np.pad(values.reshape(ny,nx,4),((1,1),(1,1),(0,0)),mode='edge')
        if z%32==0 or z==nz-1:
            print('Baked %d/%d slices'%(z+1,nz),flush=True)
    assets = Path(out)/'textures'
    assets.mkdir(parents=True,exist_ok=True)
    Image.fromarray(field).save(assets/'field.png')
    Image.fromarray(material).save(assets/'material.png')
    metadata = dict(schema_version=1,dimensions=cells.tolist(),origin=origin.tolist(),pitch=pitch,
                    atlas=[width,height],tile=[nx+2,ny+2],columns=columns,distance_range=distance_range,
                    resolution=resolution,steps=steps,shell_cells=shell,watertight=watertight,
                    sign_method='3-ray parity with thin shell' if watertight else 'unsigned surface shell; open/nonmanifold mesh',
                    gpu_bytes_rgba8=gpu_bytes,model_bounds=info['model_bounds'],bake_seconds=time.perf_counter()-start,
                    field_channels='RG signed distance uint16, BA octahedral normal',material_channels='RGB base color, A unused=255',
                    assets={p.name:dict(bytes=p.stat().st_size,sha256=digest(p)) for p in assets.glob('*.png')})
    write_json(Path(out)/'field.json',metadata)
    return metadata
