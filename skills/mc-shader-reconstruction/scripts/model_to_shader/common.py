"""Versioned model interchange and deterministic texture sampling. Offline only."""
import hashlib
import json
from pathlib import Path
import numpy as np
from PIL import Image

VERSION = 1
PRESETS = {'low': (128,160,.85,.15), 'medium': (256,224,.90,.10), 'high': (512,384,.97,.06)}

def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def unit(v):
    return v/np.maximum(np.linalg.norm(v, axis=-1, keepdims=True),1e-12)

def srgb(v):
    v = np.asarray(v)
    return np.where(v<=.0031308,12.92*v,1.055*np.maximum(v,0)**(1/2.4)-.055)

def linear(v):
    return np.where(v<=.04045,v/12.92,((v+.055)/1.055)**2.4)

def save_scene(work, vertices, faces, normals, uv, material_ids, materials, info):
    work = Path(work)
    work.mkdir(parents=True,exist_ok=True)
    v,f,n,t,m = [np.asarray(a,dtype=d) for a,d in zip(
        (vertices,faces,normals,uv,material_ids),('f4','u4','f4','f4','i4'))]
    if v.ndim!=2 or v.shape[1]!=3 or not len(v) or f.ndim!=2 or f.shape[1]!=3 or not len(f):
        raise ValueError('Empty or malformed mesh')
    if n.shape!=(len(f),3,3) or t.shape!=(len(f),3,2) or m.shape!=(len(f),):
        raise ValueError('Invalid per-corner normal/UV or face-material layout')
    if f.max()>=len(v) or m.min()<0 or m.max()>=len(materials):
        raise ValueError('Geometry/material index out of range')
    if any(not np.isfinite(a).all() for a in (v,n,t)):
        raise ValueError('Non-finite geometry, normals or UV')
    bounds = np.array([v.min(0),v.max(0)])
    span = np.ptp(bounds,axis=0).max()
    if span<=1e-20:
        raise ValueError('Zero model extent')
    # Relative degeneracy threshold: source units can be millimetres or metres.
    area = np.linalg.norm(np.cross((v[f[:,1]]-v[f[:,0]])/span,(v[f[:,2]]-v[f[:,0]])/span),axis=1)
    if np.any(area<1e-12):
        good = area>=1e-12
        info['warnings'].append('Removed %d zero-area triangles'%int((~good).sum()))
        f,n,t,m = f[good],n[good],t[good],m[good]
    if not len(f):
        raise ValueError('All triangles are degenerate')
    center = bounds.mean(0)
    center[1] = bounds[0,1]
    scale = 2./span
    v = ((v-center)*scale).astype('f4')
    n = unit(n).astype('f4')
    if np.any(np.linalg.norm(n,axis=-1)<.5):
        raise ValueError('Invalid zero normals')
    # UV seams and normal discontinuities remain per triangle corner.
    np.savez_compressed(work/'mesh.npz',vertices=v,faces=f,normals=n,uv=t,material_ids=m)
    info.update(schema_version=VERSION,vertices=len(v),triangles=len(f),materials=materials,
                source_bounds=bounds.tolist(),model_bounds=[v.min(0).tolist(),v.max(0).tolist()],
                normalization=dict(origin=center.tolist(),scale=scale,axes='right-handed Y up; xz centered; bottom y=0; longest edge=2'))
    write_json(work/'scene.json',info)

def load_scene(work):
    work = Path(work)
    info = json.loads((work/'scene.json').read_text(encoding='utf-8'))
    if info.get('schema_version')!=VERSION:
        raise ValueError('Unsupported interchange schema')
    with np.load(work/'mesh.npz',allow_pickle=False) as data:
        mesh = {k:data[k].copy() for k in data.files}
    textures = []
    for material in info['materials']:
        image = None
        if material.get('image'):
            with Image.open(work/material['image']) as im:
                image = np.asarray(im.convert('RGBA'),dtype='f4')/255.
            if image[...,3].min()<.999:
                raise ValueError('Alpha cutout/blending requires a dedicated renderer; material: '+material['name'])
        if material['color'][3]<.999:
            raise ValueError('Transparent material requires a dedicated renderer: '+material['name'])
        textures.append(image)
    return mesh,info,textures

def sample_texture(image,uv,wrap='repeat'):
    h,w = image.shape[:2]
    # Standard interchange UV: origin lower-left; image arrays start at top.
    xy = uv*np.array([w,h])-.5
    xy[:,1] = h-1-xy[:,1]
    lo = np.floor(xy).astype('i8')
    frac = xy-lo
    def indices(i,size):
        if wrap=='clamp':
            return np.clip(i,0,size-1)
        if wrap=='mirror':
            i = i%(2*size)
            return np.where(i<size,i,2*size-1-i)
        return i%size
    x0,x1 = indices(lo[:,0],w),indices(lo[:,0]+1,w)
    y0,y1 = indices(lo[:,1],h),indices(lo[:,1]+1,h)
    return ((image[y0,x0]*(1-frac[:,:1])+image[y0,x1]*frac[:,:1])*(1-frac[:,1:])
            +(image[y1,x0]*(1-frac[:,:1])+image[y1,x1]*frac[:,:1])*frac[:,1:])

def surface(mesh,info,textures,ids,bary):
    weights = np.column_stack([1-bary.sum(1),bary])
    uv = np.einsum('ni,nij->nj',weights,mesh['uv'][ids])
    normal = unit(np.einsum('ni,nij->nj',weights,mesh['normals'][ids]))
    color = np.zeros((len(ids),3),dtype='f4')
    materials = mesh['material_ids'][ids]
    for index in np.unique(materials):
        mask = materials==index
        mat = info['materials'][int(index)]
        value = np.asarray(mat['color'][:3])
        if textures[index] is not None:
            value = sample_texture(textures[index],uv[mask],mat.get('wrap','repeat'))[:,:3]*value
            if 'texture_factor_linear' in mat:
                value = srgb(linear(value)*np.asarray(mat['texture_factor_linear']))
        color[mask] = value
    return np.clip(color,0,1),normal
