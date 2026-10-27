"""Compare generated GLSL against the imported original triangles, not a proxy.

Automatic metrics are a gate; actual visual review and Minecraft remain pending.
"""
import json
from pathlib import Path
import re
import subprocess
import tempfile
import moderngl
import numpy as np
import open3d as o3d
from PIL import Image,ImageDraw
from common import load_scene,surface,unit,write_json,digest

def wrapped(source,version='330',mask=False):
    source = re.sub(r'^\s*#include[^\n]*','',source,flags=re.M)
    prefix = '#version '+version+'\nprecision highp float;\n#define LAYOUT_BINDING(x)\n'
    if version=='100':
        vertex = '#version 100\nattribute vec2 position;varying highp vec2 uv;void main(){uv=position*.5+.5;gl_Position=vec4(position,0,1);}'
        prefix += 'varying highp vec2 uv;\n'
    else:
        vertex = '#version '+version+'\nprecision highp float;in vec2 position;out vec2 uv;void main(){uv=position*.5+.5;gl_Position=vec4(position,0,1);}'
        prefix += 'in vec2 uv;out vec4 resultColor;\n#define gl_FragColor resultColor\n#define texture2D texture\n'
    if mask:
        prefix += '#define MODEL_VALIDATE_MASK\n'
    return vertex,prefix+source

def compile_sources(ctx,out,name,headers,validator):
    source = (out/(name+'.fragment')).read_text(encoding='utf-8')
    rows = []
    def expand(code,stack=()):
        def include(match):
            filename = match.group(1)
            if filename in stack:
                raise ValueError('Shader include cycle: '+filename)
            return expand((headers/filename).read_text(encoding='utf-8'),stack+(filename,))
        return re.sub(r'^\s*#include\s+"([^"]+)"[^\n]*',include,code,flags=re.M)
    for version in ('100','300 es','330'):
        if headers:
            prefix = '#version '+version+'\n#define POS4 vec4\n#define MAT4 mat4\nprecision highp float;\n'
            vertex = prefix+expand((out/(name+'.vertex')).read_text(encoding='utf-8'))
            fragment = prefix+expand(source)
        else:
            vertex,fragment = wrapped(source,version)
        if validator:
            with tempfile.TemporaryDirectory(prefix='model_shader_compile_') as tmp:
                for stage,code in (('vert',vertex),('frag',fragment)):
                    path = Path(tmp)/('shader.'+stage)
                    path.write_text(code,encoding='utf-8')
                    run = subprocess.run([str(validator),'-S',stage,str(path)],capture_output=True,text=True)
                    if run.returncode:
                        raise RuntimeError(run.stdout+run.stderr)
        ctx.program(vertex_shader=vertex,fragment_shader=fragment).release()
        rows.append(dict(version=version,driver='PASS',strict_validator='PASS' if validator else 'NOT_RUN',
                         actual_engine_headers=bool(headers)))
    return rows

class Preview:
    def __init__(self,out,name,width=640,height=360):
        self.out,self.w,self.h = Path(out),width,height
        self.mesh,self.info,self.textures = load_scene(self.out/'intermediate')
        self.ctx = moderngl.create_standalone_context()
        self.fbo = self.ctx.simple_framebuffer((width,height),components=4)
        source = (self.out/(name+'.fragment')).read_text(encoding='utf-8')
        self.vbo = self.ctx.buffer(np.array([-1,-1,1,-1,-1,1,1,1],dtype='f4').tobytes())
        self.programs,self.vaos = {},{}
        for mask in (False,True):
            vertex,fragment = wrapped(source,mask=mask)
            p = self.ctx.program(vertex_shader=vertex,fragment_shader=fragment)
            self.programs[mask] = p
            self.vaos[mask] = self.ctx.simple_vertex_array(p,self.vbo,'position')
        self.atlases = []
        for filename in ('field.png','material.png'):
            with Image.open(self.out/'textures'/filename) as image:
                t = self.ctx.texture(image.size,4,image.convert('RGBA').tobytes())
            t.filter = moderngl.LINEAR,moderngl.LINEAR
            t.repeat_x = t.repeat_y = False
            self.atlases.append(t)
        target = np.array([0,self.info['model_bounds'][1][1]*.5,0])
        self.camera = target+np.array([2.4,1.5,3.])*max(1.,1.1/(width/height))
        forward = unit(target-self.camera)
        right = unit(np.cross(forward,[0,1,0]))
        up = np.cross(right,forward)
        x,y = np.meshgrid((np.arange(width)+.5)/width*2-1,(np.arange(height)+.5)/height*2-1)
        self.rays = unit(forward+.31529879*(x[...,None]*(width/height)*right+y[...,None]*up)).astype('f4')
        self.scene = o3d.t.geometry.RaycastingScene()
        self.scene.add_triangles(o3d.core.Tensor(self.mesh['vertices'],dtype=o3d.core.Dtype.Float32),
                                 o3d.core.Tensor(self.mesh['faces'],dtype=o3d.core.Dtype.UInt32))

    def render(self,angle,mask=False,timing=False):
        self.fbo.use()
        self.ctx.viewport = 0,0,self.w,self.h
        self.ctx.disable(moderngl.DEPTH_TEST|moderngl.BLEND)
        p = self.programs[mask]
        p['EXTRA_VECTOR1'].value = angle/20.,float(self.w),float(self.h),20.
        for i,t in enumerate(self.atlases,3):
            key = 'TEXTURE_'+str(i)
            if key in p:
                p[key].value = i
            t.use(i)
        vao = self.vaos[mask]
        vao.render(moderngl.TRIANGLE_STRIP)
        samples = []
        if timing:
            for _ in range(3):
                vao.render(moderngl.TRIANGLE_STRIP)
            self.ctx.finish()
            for _ in range(5):
                with self.ctx.query(time=True) as query:
                    vao.render(moderngl.TRIANGLE_STRIP)
                self.ctx.finish()
                samples.append(query.elapsed/1e6)
        image = Image.frombytes('RGBA',(self.w,self.h),self.fbo.read(components=4,alignment=1)).transpose(Image.Transpose.FLIP_TOP_BOTTOM)
        return image,samples

    def reference(self,angle):
        c,s = np.cos(np.radians(angle)),np.sin(np.radians(angle))
        root = np.array([[c,0,s],[0,1,0],[-s,0,c]])
        origins = np.broadcast_to(self.camera@root,self.rays.shape)
        hit = self.scene.cast_rays(o3d.core.Tensor(np.concatenate([origins,self.rays@root],axis=-1).astype('f4')))
        visible = np.isfinite(hit['t_hit'].numpy())
        ids = hit['primitive_ids'].numpy()[visible]
        bary = hit['primitive_uvs'].numpy()[visible]
        albedo,normal = surface(self.mesh,self.info,self.textures,ids,bary)
        normal = unit(normal@root.T)
        light = unit(np.array([.5,.8,.7]))
        diffuse = np.maximum(normal@light,0)
        half = unit(light-self.rays[visible])
        specular = np.maximum(np.sum(normal*half,axis=1),0)**32
        rgb = albedo*(.32+.88*diffuse[:,None])+.07*specular[:,None]
        y = (np.arange(self.h)+.5)/self.h
        background = np.array([.018,.025,.042])*(1-y[:,None])+np.array([.065,.085,.12])*y[:,None]
        image = np.broadcast_to(background[:,None,:],(self.h,self.w,3)).copy()
        image[visible] = rgb
        return Image.fromarray(np.rint(image[::-1]*255).clip(0,255).astype('u1')),visible[::-1].copy()

def validate(out,name,min_iou,max_mae,headers=None,validator=None):
    out = Path(out)
    folder = out/'validation'
    folder.mkdir(exist_ok=True)
    p = Preview(out,name)
    result = dict(status='VALIDATION_FAILED',renderer=p.ctx.info['GL_RENDERER'],resolution=[p.w,p.h],
                  shader_sha256=digest(out/(name+'.fragment')),
                  criteria=dict(min_iou=min_iou,max_mae=max_mae),
                  reference='Original imported triangles, per-corner UV and normals; adapter itself is shared, not independently verified',
                  compile=compile_sources(p.ctx,out,name,headers,validator),views=[],
                  visual_review='PENDING',minecraft_runtime_tested=False,
                  timing_scope='Desktop GPU draw only; excludes readback/encoding and game; not FPS')
    contact = Image.new('RGB',(p.w*2,(p.h+24)*4))
    draw = ImageDraw.Draw(contact)
    for i,angle in enumerate((0.,90.,180.,270.)):
        image,timing = p.render(angle,timing=True)
        mask = np.array(p.render(angle,mask=True)[0])[...,0]>127
        reference,source = p.reference(angle)
        both = mask&source
        iou = float(both.sum()/max((mask|source).sum(),1))
        mae = float(np.abs(np.array(image,dtype=float)[both,:3]-np.array(reference,dtype=float)[both,:3]).mean()/255) if both.any() else 1.
        reference.save(folder/('source_%03d.png'%angle))
        image.save(folder/('shader_%03d.png'%angle))
        Image.fromarray(np.where(source[...,None],255,0).astype('u1').repeat(3,axis=2)).save(folder/('source_mask_%03d.png'%angle))
        Image.fromarray(np.where(mask[...,None],255,0).astype('u1').repeat(3,axis=2)).save(folder/('shader_mask_%03d.png'%angle))
        y = i*(p.h+24)
        contact.paste(reference,(0,y+24))
        contact.paste(image.convert('RGB'),(p.w,y+24))
        draw.text((8,y+4),'Original mesh / %d deg'%angle,fill='white')
        draw.text((p.w+8,y+4),'Generated / IoU %.4f / MAE %.4f'%(iou,mae),fill='white')
        passed = iou>=min_iou and mae<=max_mae
        result['views'].append(dict(angle=angle,iou=iou,material_mae=mae,passed=passed,
                                    foreground_pixels=int(source.sum()),gpu_samples_ms=timing,
                                    gpu_median_ms=float(np.median(timing))))
        print('Compare',angle,'IoU',round(iou,5),'MAE',round(mae,5),'PASS' if passed else 'FAIL',flush=True)
    contact.save(folder/'source_vs_shader.png')
    frames = [p.render(i*7.5)[0].convert('RGB').resize((480,270)) for i in range(48)]
    durations = [round((i+1)*100/12)*10-round(i*100/12)*10 for i in range(48)]
    frames[0].save(folder/'rotation.gif',save_all=True,append_images=frames[1:],duration=durations,loop=0,disposal=2)
    first = np.array(p.render(0)[0])
    repeat = np.array(p.render(360)[0])
    result['periodic_repeat'] = bool(np.array_equal(first,repeat))
    result['temporal_preview'] = 'Generated 48 views; human review pending'
    if all(row['passed'] for row in result['views']) and result['periodic_repeat']:
        result['status']='AUTOMATED_PASS'
    write_json(folder/'report.json',result)
    return result
